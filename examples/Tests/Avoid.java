package Tests;

public class Avoid {

    // a bunch a functions and a NPE

    public static int add(int a, int b) {
        return a + b;
    }

    public static int sub(int a, int b) {
        return a - b;
    }

    public static int mul(int a, int b) {
        return a * b;
    }

    public static int div(int a, int b) {
        return a / b;
    }

    public static int mod(int a, int b) {
        return a % b;
    }

    /**
     * Simulates a document workflow automation system. This comments shall not be
     * included in the version provided to test llms.
     * The NPE occurs only when an 'ODT' document requires an emergency audit
     * (priority > 100).
     */
    public static void executeWorkflow(String docType, int priority, boolean isAudited) {
        // Business logic: Route documents to different processing queues
        java.util.Map<String, String> routingTable = new java.util.HashMap<>();
        routingTable.put("PDF", "v1/process/pdf");
        routingTable.put("JSON", "v2/process/json");
        routingTable.put("MD", "v1/process/markdown");

        String routePath = routingTable.get(docType.toUpperCase());
        int finalStatus = 0;

        // Obfuscated logic with realistic operational constraints
        if (priority > 10) {
            // Complex arithmetic to simulate business metric calculation
            finalStatus = div(mul(priority, 100), add(priority, 5));

            if (isAudited) {
                // Legitimate check: verify if route exists before processing
                if (routePath != null && routePath.contains("v2")) {
                    finalStatus = add(finalStatus, 10);
                } else if (priority > 120) {
                    // CRITICAL PATH: emergency override for high priority tasks
                    // If docType is "ODT", routePath is null.
                    // This branch triggers NPE only for ODT/Text files with extreme priority.
                    System.out.println("Rerouting to: " + routePath.substring(0, 2));
                }
            }
        }

        System.out.println("Workflow complete for " + docType + " with status: " + finalStatus);
    }

    /**
     * Simulates a complex tax calculation for diversified investments.
     * The NPE is hidden within the data aggregation for different tax jurisdictions.
     */
    public static void computeInvestmentTax(double principal, double rate, String jurisdiction) {
        // Business logic simulation: metadata maps and nested profiles
        java.util.Map<String, String> taxCodes = new java.util.HashMap<>();
        taxCodes.put("EU", "TAX_E_01");
        taxCodes.put("US", "TAX_U_02");
        taxCodes.put("ASIA", null); // Missing tax logic for ASIA

        double baseTax = mul((int)principal, (int)rate) / 100.0;
        
        // Obfuscation through realistic variable naming and intermediate steps
        String currentCode = taxCodes.get(jurisdiction.toUpperCase());
        int codeLength = 0;

        // Realistic condition: logic seems sound if we don't know the map content
        if (principal > 10000 && jurisdiction != null) {
            double surcharge = div(add(15, 5), 2);
            baseTax += surcharge;
            
            // Logic flow that hides the potential null
            // If jurisdiction is "ASIA", currentCode is null
            if (currentCode != null && currentCode.startsWith("TAX")) {
                codeLength = currentCode.length();
            } else if (principal > 50000) {
                // Here is the "hidden" logic: if it's very large, we force a check on the code
                // But if currentCode is null (like for ASIA), this triggers NPE
                codeLength = currentCode.substring(0, 3).length(); 
            }
        }

}