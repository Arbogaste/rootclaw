package Tests;

public class ReTest {

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

    public static void executeWorkflow(String docType, int priority, boolean isAudited) {
        // Business logic: Route documents to different processing queues
        java.util.Map<String, String> routingTable = new java.util.HashMap<>();
        routingTable.put("PDF", "v1/process/pdf");
        routingTable.put("JSON", "v2/process/json");
        routingTable.put("MD", "v1/process/markdown");

        String routePath = routingTable.get(docType.toUpperCase());
        int finalStatus = 0;

        if (priority > 10) {
            finalStatus = div(mul(priority, 100), add(priority, 5));

            if (isAudited) {
                if (routePath != null && routePath.contains("v2")) {
                    finalStatus = add(finalStatus, 10);
                } else if (priority > 120) {
                    System.out.println("Rerouting to: " + routePath.substring(0, 2));
                }
            }
        }

        System.out.println("Workflow complete for " + docType + " with status: " + finalStatus);
    }
}