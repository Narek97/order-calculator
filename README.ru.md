# Order calculator — исходники кастомизации Creatio

Учебное приложение: интерфейс Freedom UI вызывает C#-сервис внутри Creatio .NET.
Целевой стенд: Studio 8.3.3, внешняя MSSQL. Это исходники, а не готовый установочный архив.
Самостоятельный ASP.NET процесс, контейнер или отдельная база этому примеру не нужны.

## Файлы

- backend/UsrOrderCalculatorService.cs — серверная схема Source code.
- frontend/UsrOrderCalculatorClient.js — клиентский модуль для вызова сервиса и обработчика кнопки.
- docs/ui-spec.json — поля формы, имя приложения и желаемый порядок навигации.

## Установка по шагам

1. Сохранить резервную копию текущей базы и изменяемого состояния Design перед установкой.
2. В Application Hub создать Records & Business Processes приложение Order calculator,
   код UsrOrderCalculator, без мобильных страниц. Проверить фактическое имя нового пакета.
3. Добавить поля из docs/ui-spec.json в веб-карточку нового приложения. В списке приложения
   можно отобразить Name, Quantity, Unit price и Total.
4. В новом пакете добавить Source code с кодом UsrOrderCalculatorService. Вставить backend/*.cs,
   Save and Publish, дождаться успешной компиляции. Не редактировать UsrTestAppService.
5. В браузере с сессией Supervisor проверить:
   https://creatio.creatio.test/rest/UsrOrderCalculatorService/Calculate?quantity=3&unitPrice=1250.50
   Ожидается CalculateResult.Success=true, Total=3751.50, Version=1.0.0.
6. Добавить клиентский модуль UsrOrderCalculatorClient. Перед подключением к Freedom UI
   получить исходный код сгенерированной страницы: названия её атрибутов могут отличаться
   от кодов колонок. Не угадывать эти названия и не заменять страницу чужим шаблоном целиком.
7. В зависимостях AMD страницы подключить UsrOrderCalculatorClient; добавить
   client.createHandler({quantity: ACTUAL_QUANTITY_ATTRIBUTE, unitPrice: ACTUAL_PRICE_ATTRIBUTE,
   total: ACTUAL_TOTAL_ATTRIBUTE, message: ACTUAL_MESSAGE_ATTRIBUTE}) в handlers.
   ACTUAL_* — пояснения в этом README, не готовые идентификаторы для вставки.
   Кнопке Calculate назначить clicked.request = usr.CalculateOrderRequest.
8. Проверить расчёт, отказ для quantity=0, сохранение и повторное открытие записи.
   Total вычисляет сервер, но в учебной форме записывает пользователь страницы. Для обязательной
   проверки суммы при любом способе записи (OData/импорт/интеграции) нужен серверный обработчик
   события сущности. Такой обработчик в этот первый пример не входит.
9. Через настройки навигации добавить новый раздел в My applications после Test app.
10. После проверки Design: Control Plane → publish order-calculator-v1 → activate →
    убедиться, что Worker Converged. Проверить сервис именно на Worker: сессия Supervisor
    через общий Gateway может направлять запросы на Design.

## Границы проверки

Локально проверяются синтаксис JS, контракт вызова и обработка ответов. Компиляция C# со сборками
Terrasoft и отображение Freedom UI проверяются на целевом Creatio. Файлы не устанавливаются
автоматически в базу или на PVC; для переносимого архива нужно экспортировать сформированный
пакет штатными инструментами Creatio. Publish версии не заменяет установку пакета и миграции БД.

## Источники

- https://academy.creatio.com/guides/dev/development-on-creatio-platform/back-end-development/web-services/web-service-implementation/custom-web-service
- https://academy.creatio.com/guides/no-code-customization/8.3/customization-tools/app-management/apps-management
