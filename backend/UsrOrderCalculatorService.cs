namespace Terrasoft.Configuration
{
    using System;
    using System.Runtime.Serialization;
    using System.ServiceModel;
    using System.ServiceModel.Activation;
    using System.ServiceModel.Web;
    using Terrasoft.Web.Common;

    [DataContract]
    public class UsrOrderCalculatorResult
    {
        [DataMember] public bool Success { get; set; }
        [DataMember] public string Message { get; set; }
        [DataMember] public decimal Total { get; set; }
        [DataMember] public string Version { get; set; }
    }

    [ServiceContract]
    [AspNetCompatibilityRequirements(
        RequirementsMode = AspNetCompatibilityRequirementsMode.Required)]
    public class UsrOrderCalculatorService : BaseService
    {
        // Read-only operation. The Creatio session authenticates the caller.
        // No SQL queries, credentials or application records are changed here.
        [OperationContract]
        [WebInvoke(Method = "GET", ResponseFormat = WebMessageFormat.Json,
            BodyStyle = WebMessageBodyStyle.Wrapped)]
        public UsrOrderCalculatorResult Calculate(int quantity, decimal unitPrice)
        {
            if (quantity < 1 || quantity > 1000000)
            {
                return Failure("Quantity must be between 1 and 1000000.");
            }
            if (unitPrice < 0m || unitPrice > 1000000000m)
            {
                return Failure("Unit price must be between 0 and 1000000000.");
            }
            if (decimal.Round(unitPrice, 2) != unitPrice)
            {
                return Failure("Unit price must have no more than two decimal places.");
            }
            return new UsrOrderCalculatorResult {
                Success = true,
                Message = "Calculated on the Creatio .NET server.",
                Total = decimal.Round(quantity * unitPrice, 2,
                    MidpointRounding.AwayFromZero),
                Version = "1.0.0"
            };
        }

        private static UsrOrderCalculatorResult Failure(string message)
        {
            return new UsrOrderCalculatorResult {
                Success = false, Message = message, Total = 0m, Version = "1.0.0"
            };
        }
    }
}
