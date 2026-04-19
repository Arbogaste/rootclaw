public class Test {

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

    public static void computeInvestmentTax(double principal, double rate, String jurisdiction) {
        // Business logic simulation: metadata maps and nested profiles
        java.util.Map<String, String> taxCodes = new java.util.HashMap<>();
        taxCodes.put("EU", "TAX_E_01");
        taxCodes.put("US", "TAX_U_02");
        taxCodes.put("ASIA", null);

        double baseTax = mul((int) principal, (int) rate) / 100.0;

        String currentCode = taxCodes.get(jurisdiction.toUpperCase());
        int codeLength = 0;

        if (principal > 10000 && jurisdiction != null) {
            double surcharge = div(add(15, 5), 2);
            baseTax += surcharge;

            if (currentCode != null && currentCode.startsWith("TAX")) {
                codeLength = currentCode.length();
            } else if (principal > 50000) {
                codeLength = currentCode.substring(0, 3).length();
            }
        }

        System.out.println("Computed Tax for " + jurisdiction + ": " + baseTax + " (Code: " + codeLength + ")");
    }
}