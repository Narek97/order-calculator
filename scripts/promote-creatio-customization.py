#!/usr/bin/env python3
"""Publish, activate and verify the current Design customization."""
import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://operator.creatio.test"
TOKEN_URL = "https://identity.creatio.test/connect/token"
INSTANCE = "/api/v1/instances/creatio-runtime/customizations"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self):
        self.client_id = os.environ["CONTROL_PLANE_CLIENT_ID"]
        self.secret = os.environ["CONTROL_PLANE_CLIENT_SECRET"]
        if not self.client_id or not self.secret:
            raise RuntimeError("Control Plane credentials are missing")
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        self.token = None
        self.expiry = 0
        self.deadline = time.monotonic() + 1800

    def send(self, url, data=None, headers=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "Promotion timed out; inspect recorded operations before retrying"
            )
        request = urllib.request.Request(url, data=data, headers=headers or {})
        with self.opener.open(request, timeout=min(30, remaining)) as response:
            return response.status, json.load(response)

    def authorize(self):
        _, result = self.send(
            TOKEN_URL,
            urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.secret,
                "scope": "creatio_k8s_control_plane_api",
            }).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.token = result["access_token"]
        self.expiry = time.monotonic() + max(
            1, int(result.get("expires_in", 300)) - 30
        )

        # Diagnostic inspection; the API validates the signed token.
        part = self.token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(
            part + "=" * (-len(part) % 4)
        ))
        permissions = claims.get("permission", [])
        if isinstance(permissions, str):
            permissions = [permissions]
        if set(permissions) != {"control_plane.read", "control_plane.deploy"}:
            raise RuntimeError("Expected the dedicated CI read/deploy permissions")

    def call(self, route, payload=None):
        for attempt in range(2):
            if not self.token or time.monotonic() >= self.expiry:
                self.authorize()
            headers = {"Authorization": "Bearer " + self.token}
            data = None
            if payload is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(payload).encode()
            try:
                status, result = self.send(API + route, data, headers)
                expected = 202 if payload is not None else 200
                if status != expected or not isinstance(result, dict):
                    raise RuntimeError(f"Unexpected API response for {route}")
                return result
            except urllib.error.HTTPError as error:
                if error.code == 401 and attempt == 0:
                    self.expiry = 0
                    continue
                raise
        raise RuntimeError("Authentication retry failed")


def execute(client, action, payload):
    accepted = client.call(INSTANCE + "/" + action, payload)
    operation_id = accepted["operationId"]
    route = "/api/v1/operations/" + urllib.parse.quote(operation_id, safe="")
    print(f"{action}: operation {operation_id}", flush=True)
    previous = None
    last_log = 0

    while True:
        status = client.call(route)["status"]
        state = status["state"]
        progress = (state, status.get("stage"))
        if progress != previous or time.monotonic() - last_log >= 30:
            print(f"{action}: {progress}", flush=True)
            previous = progress
            last_log = time.monotonic()
        if state == "Succeeded":
            return operation_id
        if state in {"Failed", "Rejected", "Blocked"}:
            error = status.get("error") or {}
            raise RuntimeError(
                f"{action} {state}: {error.get('code', '')}; "
                f"inspect operation {operation_id}"
            )
        if state not in {"Accepted", "Running", "PendingApproval"}:
            raise RuntimeError(f"Unexpected operation state: {state}")
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--customization-version", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    version = args.customization_version
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?", version):
        raise RuntimeError("Invalid customization version name")

    client = Client()
    current = client.call(INSTANCE + "/status")
    print("Control Plane access verified.", flush=True)
    print("Currently active:", current.get("activeCustomizationVersion"), flush=True)
    if not args.apply:
        print("Preflight only; no customization changed.")
        return

    execute(client, "publish", {
        "customizationVersion": version,
        "impactClassification": "Unknown",
        "idempotencyKey": version + ":publish",
        "notes": (
            f"GitHub deployment {os.environ.get('GITHUB_RUN_ID', 'manual')}; "
            f"build {os.environ.get('SOURCE_BUILD_RUN_ID', 'unspecified')}"
        ),
        "activateOnSuccess": False,
    })
    execute(client, "activate", {
        "customizationVersion": version,
        "cacheActivationMode": "None",
        "expectedRestartClass": "RecycleWorkers",
        "markKnownGoodOnSuccess": False,
    })
    execute(client, "verify", {
        "customizationVersion": version,
        "markKnownGoodOnSuccess": False,
    })

    while True:
        status = client.call(INSTANCE + "/status")
        workers = status.get("workerConvergence") or []
        topology = status.get("topology") or {}
        expected = int(topology.get("workerReplicas") or 0)
        converged = (
            status.get("activeCustomizationVersion") == version
            and expected > 0
            and len(workers) == expected
            and int(topology.get("workerReadyReplicas") or 0) == expected
            and int(status.get("failedReplicas") or 0) == 0
            and all(
                worker.get("ready") is True
                and worker.get("artifactVersion") == version
                and worker.get("state", "").lower() == "converged"
                for worker in workers
            )
        )
        if converged:
            print(f"OK: {expected} Workers converged on {version}", flush=True)
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a") as stream:
                    stream.write(
                        f"\n### Creatio promotion\n"
                        f"- Version: `{version}`\n"
                        f"- Converged Workers: {expected}\n"
                    )
            return
        print("Waiting for the active-version and Worker status to converge...", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"STOP: HTTP {error.code} on "
            f"{urllib.parse.urlsplit(error.url).path}"
        )
    except (urllib.error.URLError, RuntimeError, ValueError, TimeoutError) as error:
        raise SystemExit(f"STOP: {error}")
