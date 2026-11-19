/* Creatio client module. Register this as UsrOrderCalculatorClient.
 * Wire it into the generated Freedom UI page after inspecting its real attributes.
 * No browser-side business calculation: the result comes from the C# service.
 */
define("UsrOrderCalculatorClient", [], function () {
    "use strict";

    async function calculate(quantity, unitPrice) {
        if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > 1000000) {
            throw new Error("Quantity must be a whole number between 1 and 1000000.");
        }
        if (!Number.isFinite(unitPrice) || unitPrice < 0 || unitPrice > 1000000000) {
            throw new Error("Enter a valid non-negative unit price.");
        }
        const query = new URLSearchParams({
            quantity: String(quantity), unitPrice: String(unitPrice)
        });
        const response = await fetch(
            "/rest/UsrOrderCalculatorService/Calculate?" + query.toString(),
            { method: "GET", credentials: "same-origin", cache: "no-store",
              headers: { Accept: "application/json" } }
        );
        if (response.redirected || !response.ok ||
            !(response.headers.get("content-type") || "").includes("application/json")) {
            throw new Error("Service unavailable or session expired (HTTP " + response.status + ").");
        }
        const body = await response.json();
        const result = body && body.CalculateResult;
        if (!result || typeof result.Success !== "boolean") {
            throw new Error("Unexpected server response.");
        }
        if (!result.Success) {
            throw new Error(result.Message || "Calculation rejected by server.");
        }
        if (!Number.isFinite(result.Total)) {
            throw new Error("Server returned an invalid total.");
        }
        return result;
    }

    // attribute names must come from the actual generated page schema.
    function createHandler(attributes) {
        if (!attributes || !attributes.quantity || !attributes.unitPrice || !attributes.total) {
            throw new Error("Actual page attribute bindings are required.");
        }
        return {
            request: "usr.CalculateOrderRequest",
            handler: async function (request) {
                const context = request.$context;
                try {
                    const quantity = Number(await context[attributes.quantity]);
                    const unitPrice = Number(await context[attributes.unitPrice]);
                    const result = await calculate(quantity, unitPrice);
                    context[attributes.total] = result.Total;
                    if (attributes.message) { context[attributes.message] = result.Message; }
                    return result;
                } catch (error) {
                    if (attributes.message) { context[attributes.message] = error.message; }
                    else { throw error; }
                }
            }
        };
    }
    return { calculate: calculate, createHandler: createHandler };
});
