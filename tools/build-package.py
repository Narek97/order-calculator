#!/usr/bin/env python3
"""Build the lab package from an actual Creatio export and local C#/JS sources."""
import argparse
from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

PACKAGE='UsrOrderCalculator'
SERVICE='UsrOrderCalculatorService'
PAGE='UsrOrderCalculator_FormPage'

def unpack(data):
    raw=gzip.decompress(data)
    files=OrderedDict()
    pos=0
    while pos<len(raw):
        if pos+4>len(raw): raise ValueError('Truncated filename length')
        count=struct.unpack_from('<i',raw,pos)[0];pos+=4
        if not 0<count<=4096 or pos+count*2+4>len(raw): raise ValueError('Invalid filename length')
        name=raw[pos:pos+count*2].decode('utf-16le');pos+=count*2
        safe=PurePosixPath(name.replace('\\','/'))
        if safe.is_absolute() or '..' in safe.parts or ':' in name or name in files: raise ValueError('Unsafe or duplicate name')
        size=struct.unpack_from('<i',raw,pos)[0];pos+=4
        if size<0 or pos+size>len(raw): raise ValueError('Truncated content')
        files[name]=raw[pos:pos+size];pos+=size
    return files

def pack(files):
    blocks=[]
    for name,data in files.items():
        encoded=name.encode('utf-16le')
        blocks.extend([struct.pack('<i',len(encoded)//2),encoded,struct.pack('<i',len(data)),data])
    return gzip.compress(b''.join(blocks),mtime=0)

def encoded(value):
    return json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')

def patch_page(source,client):
    # Preserve the real generated page and its bindings; only add calculator components.
    factory_start='function/**SCHEMA_ARGS*/()/**SCHEMA_ARGS*/ {'
    if source.count(factory_start)!=1: raise ValueError('Unexpected AMD factory')
    client_body=client.split('function () {',1)[1].rsplit('});',1)[0]
    source=source.replace(factory_start,factory_start+'\nconst OrderCalculatorClient = (function () {'+client_body+'})();\n',1)
    insertions=[]
    for index,(name,label,attribute,readonly) in enumerate([
        ('UsrCalculatorQuantity','Quantity','UsrCalcQuantity',False),
        ('UsrCalculatorPrice','Unit price','UsrCalcUnitPrice',False),
        ('UsrCalculatorTotal','Total','UsrCalcTotal',True),
    ]):
        insertions.append({'operation':'insert','name':name,'values':{'type':'crt.NumberInput','label':label,'control':'$'+attribute,'readonly':readonly,'labelPosition':'auto','layoutConfig':{'column':1,'row':index+2,'colSpan':1,'rowSpan':1}},'parentName':'SideAreaProfileContainer','propertyName':'items','index':index+1})
    insertions.extend([
        {'operation':'insert','name':'UsrCalculateOrderButton','values':{'type':'crt.Button','caption':'Calculate','color':'primary','clicked':{'request':'usr.CalculateOrderRequest'},'layoutConfig':{'column':1,'row':5,'colSpan':1,'rowSpan':1}},'parentName':'SideAreaProfileContainer','propertyName':'items','index':4},
        {'operation':'insert','name':'UsrCalculatorMessage','values':{'type':'crt.Label','caption':'$UsrCalcMessage','labelType':'body','labelEllipsis':False,'labelColor':'#344054','layoutConfig':{'column':1,'row':6,'colSpan':1,'rowSpan':1}},'parentName':'SideAreaProfileContainer','propertyName':'items','index':5},
    ])
    def patch_json_section(text,marker,change):
        pattern=re.compile(r'/\*\*'+marker+r'\*/(.*?)/\*\*'+marker+r'\*/',re.S)
        matches=list(pattern.finditer(text))
        if len(matches)!=1: raise ValueError('Missing unique section '+marker)
        value=json.loads(matches[0].group(1))
        value=change(value)
        return text[:matches[0].start(1)]+json.dumps(value,ensure_ascii=False,indent=2)+text[matches[0].end(1):]
    source=patch_json_section(source,'SCHEMA_VIEW_CONFIG_DIFF',lambda v:v+insertions)
    def attributes(v):
        target=v.setdefault('attributes',{})
        for name in ['UsrCalcQuantity','UsrCalcUnitPrice','UsrCalcTotal','UsrCalcMessage']:
            if name in target: raise ValueError('Attribute already exists')
            target[name]={}
        return v
    source=patch_json_section(source,'SCHEMA_VIEW_MODEL_CONFIG',attributes)
    handler='''[
        {
            request: "crt.HandleViewModelInitRequest",
            handler: async function(request, next) {
                const result = await next?.handle(request);
                request.$context.UsrCalcQuantity = 1;
                request.$context.UsrCalcUnitPrice = 0;
                request.$context.UsrCalcTotal = 0;
                request.$context.UsrCalcMessage = "Enter quantity and unit price, then click Calculate.";
                return result;
            }
        },
        OrderCalculatorClient.createHandler({
            quantity: "UsrCalcQuantity", unitPrice: "UsrCalcUnitPrice",
            total: "UsrCalcTotal", message: "UsrCalcMessage"
        })
    ]'''
    pattern=re.compile(r'(/\*\*SCHEMA_HANDLERS\*/)(.*?)(/\*\*SCHEMA_HANDLERS\*/)',re.S)
    if len(list(pattern.finditer(source)))!=1 or json.loads(pattern.search(source).group(2))!=[]:
        raise ValueError('Existing handlers require explicit merge')
    return pattern.sub(lambda m:m.group(1)+handler+m.group(3),source)

def build(project,archive,out):
    project=Path(project).resolve();archive=Path(archive).resolve();out=Path(out).resolve()
    if out.exists(): raise ValueError('Output exists: '+str(out))
    with zipfile.ZipFile(archive) as z:
        if z.namelist()!=[PACKAGE+'.gz']: raise ValueError('Unexpected ZIP contents')
        original=z.read(PACKAGE+'.gz')
    files=unpack(original)
    if unpack(pack(files))!=files: raise ValueError('Original round-trip failed')
    descriptor=json.loads(files['descriptor.json'].decode('utf-8-sig'))['Descriptor']
    if descriptor['Name']!=PACKAGE: raise ValueError('Wrong package')
    package_uid=descriptor['UId']
    service_uid=str(uuid.uuid5(uuid.UUID(package_uid),SERVICE))
    if any(path.startswith('Schemas/'+SERVICE+'/') for path in files):
        raise ValueError('Service already present; review before replacing')
    now='/Date('+str(int(time.time()*1000))+')/'
    files['Schemas/'+SERVICE+'/descriptor.json']=encoded({'Descriptor':{'UId':service_uid,'Name':SERVICE,'ModifiedOnUtc':now,'ManagerName':'SourceCodeSchemaManager','Caption':'Order calculator service','DependsOn':[]}})
    # Structure matches the public clio Source code schema template.
    files['Schemas/'+SERVICE+'/metadata.json']=encoded({'MetaData':{'Schema':{'ManagerName':'SourceCodeSchemaManager','UId':service_uid,'A2':SERVICE,'A5':package_uid,'B1':[],'B2':[],'B3':[],'B6':package_uid,'HD1':'50E3ACC0-26FC-4237-A095-849A1D534BD3'}}})
    files['Schemas/'+SERVICE+'/properties.json']=encoded({'Properties':{}})
    files['Schemas/'+SERVICE+'/'+SERVICE+'.cs']=(project/'backend'/ (SERVICE+'.cs')).read_bytes()
    for culture in ['en-US','ru-RU']:
        text='<?xml version="1.0" encoding="utf-8"?><Resources Culture="'+culture+'"><Group Type="String"><Items><Item Name="Caption" Value="Order calculator service" /></Items></Group></Resources>'
        ET.fromstring(text)
        files['Resources/'+SERVICE+'.SourceCode/resource.'+culture+'.xml']=text.encode()
    page_path='Schemas/'+PAGE+'/'+PAGE+'.js'
    source=files[page_path].decode('utf-8-sig')
    client=(project/'frontend/UsrOrderCalculatorClient.js').read_text()
    patched=patch_page(source,client)
    files[page_path]=patched.encode()
    app=json.loads(files['Files/app-descriptor.json'].decode('utf-8-sig'))
    app['Version']='1.0.1'
    app['Description']='Training order calculator: Freedom UI calls a C# service. Calculation inputs/results are not persisted.'
    files['Files/app-descriptor.json']=encoded(app)
    with tempfile.TemporaryDirectory(prefix='creatio-package-js.') as temp:
        path=Path(temp)/'page.js';path.write_text(patched)
        subprocess.run(['node','--check',str(path)],check=True)
    compressed=pack(files)
    if unpack(compressed)!=files: raise ValueError('Output round-trip failed')
    out.mkdir(parents=True)
    package=out/'package'/PACKAGE
    for name,data in files.items():
        target=package/PurePosixPath(name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    zip_path=out/(PACKAGE+'-1.0.1.zip')
    with zipfile.ZipFile(zip_path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(PACKAGE+'.gz',compressed)
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip() is not None or unpack(z.read(PACKAGE+'.gz'))!=files:
            raise ValueError('Final ZIP verification failed')
    report={'baseArchive':str(archive),'baseSHA256':hashlib.sha256(archive.read_bytes()).hexdigest(),'outputArchive':str(zip_path),'outputSHA256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'packageName':PACKAGE,'packageUId':package_uid,'serviceUId':service_uid,'fileCount':len(files),'addedService':SERVICE,'modifiedPage':PAGE,'databaseSchemaChanges':False,'calculationValuesPersisted':False,'validation':{'archiveRoundTrip':True,'zipCRC':True,'javascriptSyntax':True,'creatioInstallation':'not yet tested','csharpCompilation':'not yet tested'}}
    (out/'build-report.json').write_bytes(encoded(report))
    (out/'SHA256SUMS').write_text(report['outputSHA256']+'  '+zip_path.name+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--base',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();build(a.project,a.base,a.output)
