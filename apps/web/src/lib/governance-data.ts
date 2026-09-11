// Dedicated governance data model and records for Governance & Agent Control

export type GovernanceMetricCard = {
  key: string;
  label: string;
  value: number;
  trend: string;
  trendDir: "up" | "down";
  trendType: "good" | "bad";
  iconName: string;
};

export type LifecycleDistributionItem = {
  key: string;
  label: string;
  count: number;
  percent: number;
  color: string;
};

export type GovernanceActivity = {
  id: string;
  title: string;
  subtitle: string;
  timeAgo: string;
  iconType: "approved" | "alert" | "review" | "blocked" | "policy";
};

export type PendingHumanAction = {
  id: string;
  agentName: string;
  type: string;
  requestedBy: string;
  waitingSince: string;
  priority: "Tinggi" | "Sedang" | "Rendah";
};

export type RiskBlockerItem = {
  id: string;
  title: string;
  description: string;
  count: number;
  color: "red" | "amber" | "orange" | "yellow";
};

export type ReleaseRequestItem = {
  id: string;
  agentKey: string;
  agentName: string;
  iconName: "clock" | "users" | "settings" | "file";
  iconColor: string;
  iconBg: string;
  version: string;
  requester: string;
  status: "IN_REVIEW" | "APPROVED" | "REJECTED" | "DRAFT" | "RELEASED";
  submitted: string;
  updated: string;
  actionLabel: "View" | "Continue" | "Release" | "Activate";
};

export type AgentDirectoryItem = {
  id: string;
  agentKey: string;
  agentName: string;
  purpose: string;
  iconName: "search_file" | "file" | "clock" | "users" | "chart";
  version: string;
  scope: string;
  risk: "LOW" | "MEDIUM" | "HIGH";
  status: "ACTIVE" | "IN_REVIEW" | "DRAFT" | "SUSPENDED";
  lastRun: string;
  updated: string;
};

export type TestEvidenceItem = {
  id: string;
  agentName: string;
  agentKey: string;
  category: "POSITIVE" | "NEGATIVE" | "REGRESSION" | "SECURITY" | "RECOVERY";
  testKey: string;
  expected: "SUCCESS" | "BLOCKED" | "ERROR" | "DETECTED";
  actual: "SUCCESS" | "BLOCKED" | "FAILED" | "NOT RUN" | "DETECTED" | "PENDING";
  status: "PASSED" | "FAILED" | "BLOCKED" | "NOT RUN" | "PENDING";
  lastRun: string;
};

export type AgentPermissionItem = {
  id: string;
  agentName: string;
  agentKey: string;
  permission: string;
  capability: string;
  accessMode: "Read" | "Create" | "Write" | "Admin";
  status: "APPROVED" | "PENDING" | "REJECTED";
  approvedBy: string;
  actionLabel: "View" | "Review";
};

export type RuntimeMonitoringItem = {
  id: string;
  runId: string;
  agentName: string;
  agentKey: string;
  version: string;
  status: "SUCCESS" | "FAILED" | "BLOCKED";
  tokens: string;
  costUsd: string;
  latency: string;
  time: string;
};

export type BudgetOverviewData = {
  percentage: number;
  usedAmount: string;
  totalAmount: string;
  dailyLimits: {
    requestLimit: { used: string; max: string; percent: number };
    outputTokenLimit: { used: string; max: string; percent: number };
    costLimit: { used: string; max: string; percent: number };
  };
  alerts: {
    id: string;
    type: "info" | "warning";
    title: string;
    subtitle: string;
    timeAgo: string;
  }[];
};

export type KillSwitchAgent = {
  agentKey: string;
  agentName: string;
  scope: string;
  status: "OPERATIONAL" | "HALTED" | "DEGRADED";
  currentVersion: string;
  previousStableVersion: string;
  availableVersions: string[];
  circuitState: "CLOSED" | "OPEN" | "HALF_OPEN";
  lastHaltedAt?: string;
  haltReason?: string;
  latencyAnomaly?: string;
};

export type RollbackLogItem = {
  id: string;
  agentKey: string;
  agentName: string;
  fromVersion: string;
  toVersion: string;
  reason: string;
  executedBy: string;
  executedAt: string;
  status: "SUCCESS" | "VERIFIED" | "FAILED";
};

export type KillSwitchSystemState = {
  globalHalted: boolean;
  globalHaltReason: string;
  globalHaltedAt?: string;
  globalHaltedBy?: string;
  activeAgentsCount: number;
  haltedAgentsCount: number;
  openAnomaliesCount: number;
  mttrMinutes: number;
  agents: KillSwitchAgent[];
  rollbackHistory: RollbackLogItem[];
};

export type AuditTrailRecord = {
  id: string;
  hash: string;
  action: string;
  actionTitle: string;
  severity: "CRITICAL" | "WARNING" | "INFO" | "SUCCESS";
  actor: {
    name: string;
    role: string;
    kind: "HUMAN" | "SYSTEM";
    avatar: string;
  };
  entityType: string;
  entityId: string;
  reason: string;
  occurredAt: string;
  metadata: {
    ipAddress?: string;
    correlationId?: string;
    prevValue?: string;
    newValue?: string;
    signature?: string;
    details?: string;
    [key: string]: unknown;
  };
};

export const mockGovernanceData = {
  metrics: [
    { key: "total", label: "Total Agents", value: 28, trend: "+4 dari minggu lalu", trendDir: "up", trendType: "good", iconName: "users" },
    { key: "draft", label: "Draft", value: 6, trend: "+2 dari minggu lalu", trendDir: "up", trendType: "good", iconName: "file" },
    { key: "in_review", label: "In Review", value: 8, trend: "-1 dari minggu lalu", trendDir: "down", trendType: "bad", iconName: "clock" },
    { key: "active", label: "Active", value: 12, trend: "+3 dari minggu lalu", trendDir: "up", trendType: "good", iconName: "play" },
    { key: "suspended", label: "Suspended", value: 2, trend: "+1 dari minggu lalu", trendDir: "up", trendType: "bad", iconName: "pause" },
    { key: "pending_reviews", label: "Pending Reviews", value: 8, trend: "-2 dari minggu lalu", trendDir: "down", trendType: "good", iconName: "hourglass" },
    { key: "failed_tests", label: "Failed Tests", value: 4, trend: "+1 dari minggu lalu", trendDir: "up", trendType: "bad", iconName: "alert" },
    { key: "blocked_runtime", label: "Blocked Runtime", value: 3, trend: "+1 dari minggu lalu", trendDir: "up", trendType: "bad", iconName: "ban" },
  ] as GovernanceMetricCard[],
  distribution: [
    { key: "active", label: "Active", count: 12, percent: 43, color: "#0d5e42" },
    { key: "in_review", label: "In Review", count: 6, percent: 21, color: "#f59e0b" },
    { key: "draft", label: "Draft", count: 4, percent: 14, color: "#94a3b8" },
    { key: "suspended", label: "Suspended", count: 2, percent: 7, color: "#f87171" },
    { key: "blocked", label: "Blocked", count: 3, percent: 11, color: "#6ee7b7" },
    { key: "archived", label: "Archived", count: 1, percent: 4, color: "#cbd5e1" },
  ] as LifecycleDistributionItem[],
  activities: [
    {
      id: "act-1",
      title: "Agent PROD-ChatOps disetujui untuk production",
      subtitle: "oleh Andi Pratama",
      timeAgo: "2 jam yang lalu",
      iconType: "approved",
    },
    {
      id: "act-2",
      title: "Kegagalan uji keamanan pada agent Data-Analyst",
      subtitle: "Test: Prompt Injection Resistance",
      timeAgo: "4 jam yang lalu",
      iconType: "alert",
    },
    {
      id: "act-3",
      title: "Agent Marketing-AI dikirim untuk review",
      subtitle: "oleh Siti Rahma",
      timeAgo: "6 jam yang lalu",
      iconType: "review",
    },
    {
      id: "act-4",
      title: "Runtime agent ContentGen diblokir",
      subtitle: "Alasan: Kebijakan data eksternal",
      timeAgo: "9 jam yang lalu",
      iconType: "blocked",
    },
    {
      id: "act-5",
      title: "Policy update diterapkan: Data Handling v2.1",
      subtitle: "oleh Sistem",
      timeAgo: "1 hari yang lalu",
      iconType: "policy",
    },
  ] as GovernanceActivity[],
  pendingActions: [
    {
      id: "act-h-1",
      agentName: "Customer-Support-AI",
      type: "Production Approval",
      requestedBy: "Budi Santoso",
      waitingSince: "10 Sep 2026",
      priority: "Tinggi",
    },
    {
      id: "act-h-2",
      agentName: "Data-Analyst",
      type: "Security Review",
      requestedBy: "Siti Rahma",
      waitingSince: "11 Sep 2026",
      priority: "Sedang",
    },
    {
      id: "act-h-3",
      agentName: "Marketing-AI",
      type: "Policy Exception",
      requestedBy: "Andi Pratama",
      waitingSince: "11 Sep 2026",
      priority: "Sedang",
    },
    {
      id: "act-h-4",
      agentName: "HR-Assistant",
      type: "Model Change",
      requestedBy: "Rina Putri",
      waitingSince: "12 Sep 2026",
      priority: "Rendah",
    },
  ] as PendingHumanAction[],
  riskBlockers: [
    {
      id: "risk-1",
      title: "High Risk Agents",
      description: "Agents dengan risiko tinggi memerlukan perhatian segera.",
      count: 3,
      color: "red",
    },
    {
      id: "risk-2",
      title: "Policy Violations (7 hari)",
      description: "Pelanggaran kebijakan terdeteksi pada agent dan runtime.",
      count: 5,
      color: "amber",
    },
    {
      id: "risk-3",
      title: "Blocked Runtimes",
      description: "Agent diblokir dari eksekusi karena risiko atau pelanggaran.",
      count: 3,
      color: "orange",
    },
    {
      id: "risk-4",
      title: "Failed Security Tests (7 hari)",
      description: "Agent yang gagal dalam pengujian keamanan.",
      count: 4,
      color: "yellow",
    },
  ] as RiskBlockerItem[],
  agentControl: {
    selectedAgentKey: "EVIDENCE_CHECKER",
    agents: [
      {
        agentKey: "EVIDENCE_CHECKER",
        name: "Evidence Checker",
        version: "v0.1.0",
        lifecycleStatus: "ACTIVE",
        purpose: "Memverifikasi kelengkapan evidence task dan dokumen.",
        scope: "Property",
        riskLevel: "LOW",
        owner: "Property Division",
        createdAt: "01 Sep 2025",
        lastUpdatedAt: "09 Sep 2025 06:41",
        capabilities: ["task.read", "evidence.read", "document.read"],
        readinessChecklist: [
          { label: "Contract Valid", status: "Valid", passed: true },
          { label: "Tools Configured", status: "Completed", passed: true },
          { label: "Permissions Approved", status: "Approved", passed: true },
          { label: "All Tests Passed", status: "Passed", passed: true },
          { label: "Business Review Approved", status: "Approved", passed: true },
          { label: "Technical Review Approved", status: "Approved", passed: true },
        ],
        isReady: true,
        readyMessageTitle: "Agent siap digunakan",
        readyMessageSubtitle: "Semua persyaratan governance terpenuhi.",
        contract: {
          inputSchema: '{\n  "task_id": "string",\n  "evidence_document_ids": ["string"],\n  "verification_rules": ["string"]\n}',
          outputSchema: '{\n  "compliance_status": "COMPLIANT" | "NON_COMPLIANT",\n  "missing_evidence": ["string"],\n  "confidence_score": 0.98\n}',
          invariants: [
            "Zero writes to production database (Read-only verification mode)",
            "Strict deterministic verification logic without generative hallucinations",
            "PII and customer telephone numbers automatically masked from audit traces",
          ],
          slaLatencyMs: 450,
          maxOutputTokens: 2048,
          modelBinding: "gemini-1.5-pro (deterministic seed locked)",
        },
        tools: [
          { key: "task_reader", name: "Property Task Reader", permission: "task.read", accessMode: "READ_ONLY", status: "APPROVED" },
          { key: "evidence_validator", name: "Evidence Integrity Validator", permission: "evidence.read", accessMode: "READ_ONLY", status: "APPROVED" },
          { key: "document_parser", name: "PDF & Image OCR Parser", permission: "document.read", accessMode: "READ_ONLY", status: "APPROVED" },
        ],
        tests: [
          { testName: "Prompt Injection Resistance Test", category: "Security", result: "PASSED", score: "100%", date: "08 Sep 2025" },
          { testName: "Evidence Completeness Verification Benchmark", category: "Accuracy", result: "PASSED", score: "99.4%", date: "08 Sep 2025" },
          { testName: "Latency SLA Benchmark (< 500ms)", category: "Performance", result: "PASSED", score: "340ms avg", date: "07 Sep 2025" },
          { testName: "Zero-Hallucination False Positive Evaluation", category: "Robustness", result: "PASSED", score: "0.0% error", date: "07 Sep 2025" },
        ],
        runtime: {
          totalRuns: 1842,
          avgLatencyMs: 382,
          errorRate: "0.05%",
          lastRunAt: "09 Sep 2025 06:41",
          recentRuns: [
            { runId: "run-ev-9812", status: "SUCCEEDED", tokens: 520, latencyMs: 340, timestamp: "09 Sep 2025 06:41" },
            { runId: "run-ev-9811", status: "SUCCEEDED", tokens: 810, latencyMs: 410, timestamp: "09 Sep 2025 05:22" },
            { runId: "run-ev-9810", status: "SUCCEEDED", tokens: 490, latencyMs: 320, timestamp: "09 Sep 2025 03:15" },
            { runId: "run-ev-9809", status: "SUCCEEDED", tokens: 670, latencyMs: 395, timestamp: "08 Sep 2025 22:50" },
          ],
        },
        auditHistory: [
          { version: "v0.1.0", event: "Production Release Approval", actor: "Direktur (Bambang Soedarmono)", date: "09 Sep 2025 06:41", hash: "sha256:7f3a9e04bb82...b210" },
          { version: "v0.1.0-rc2", event: "Security & Governance Audit Passed", actor: "Security Admin (Andi Pratama)", date: "08 Sep 2025 18:20", hash: "sha256:4c12d8a0c241...f89a" },
          { version: "v0.1.0-rc1", event: "Evaluation Benchmark Suite 100% Passed", actor: "Automated CI/CD Governance Pipeline", date: "07 Sep 2025 14:00", hash: "sha256:1a89c2fa1239...09e1" },
          { version: "v0.0.1", event: "Initial Agent Contract Registration", actor: "Property Division (Hendra Wijaya)", date: "01 Sep 2025 09:12", hash: "sha256:9b33fe7194aa...7712" },
        ],
      },
      {
        agentKey: "CUSTOMER_SUPPORT_AI",
        name: "Customer Support AI",
        version: "v1.2.0",
        lifecycleStatus: "IN_REVIEW",
        purpose: "Melayani tiket customer perumahan dan eskalasi keluhan unit.",
        scope: "Customer Relations",
        riskLevel: "MEDIUM",
        owner: "Sales & Marketing",
        createdAt: "15 Jan 2025",
        lastUpdatedAt: "10 Sep 2026 10:15",
        capabilities: ["ticket.read", "ticket.write", "customer.contact"],
        readinessChecklist: [
          { label: "Contract Valid", status: "Valid", passed: true },
          { label: "Tools Configured", status: "Completed", passed: true },
          { label: "Permissions Approved", status: "Approved", passed: true },
          { label: "All Tests Passed", status: "In Review", passed: false },
          { label: "Business Review Approved", status: "Pending", passed: false },
          { label: "Technical Review Approved", status: "Approved", passed: true },
        ],
        isReady: false,
        readyMessageTitle: "Menunggu Peninjauan Bisnis",
        readyMessageSubtitle: "Memerlukan persetujuan akhir Lead Sales & Marketing.",
        contract: {
          inputSchema: '{\n  "ticket_id": "string",\n  "message": "string",\n  "priority": "HIGH" | "NORMAL"\n}',
          outputSchema: '{\n  "response": "string",\n  "escalate_to_human": "boolean"\n}',
          invariants: [
            "Tidak memberikan janji kompensasi finansial tanpa otorisasi",
            "Eskalasi wajib ke CS Human jika mendeteksi keluhan legal",
          ],
          slaLatencyMs: 800,
          maxOutputTokens: 3000,
          modelBinding: "gemini-1.5-flash",
        },
        tools: [
          { key: "ticket_api", name: "CRM Ticketing Service", permission: "ticket.write", accessMode: "READ_WRITE", status: "APPROVED" },
          { key: "faq_kb", name: "Customer FAQ Knowledge Base", permission: "ticket.read", accessMode: "READ_ONLY", status: "APPROVED" },
        ],
        tests: [
          { testName: "Customer Sentiment Empathy Test", category: "Quality", result: "PASSED", score: "96%", date: "09 Sep 2026" },
          { testName: "Policy Violation Redirection", category: "Safety", result: "PASSED", score: "100%", date: "09 Sep 2026" },
        ],
        runtime: {
          totalRuns: 4320,
          avgLatencyMs: 620,
          errorRate: "0.12%",
          lastRunAt: "10 Sep 2026 10:15",
          recentRuns: [
            { runId: "run-cs-110", status: "SUCCEEDED", tokens: 1200, latencyMs: 610, timestamp: "10 Sep 2026 10:15" },
          ],
        },
    auditHistory: [
            { version: "v1.2.0-rc1", event: "Submitted for Production Approval", actor: "Siti Rahma", date: "10 Sep 2026 10:15", hash: "sha256:3381a...9921" },
          ],
        },
    ],
    releaseRequests: [
      {
        id: "rel-01",
        agentKey: "PERMIT_OVERDUE_MONITOR",
        agentName: "Permit Overdue Monitor",
        iconName: "clock",
        iconColor: "#d97706",
        iconBg: "#fef3c7",
        version: "v0.1.0",
        requester: "Property Lead",
        status: "IN_REVIEW",
        submitted: "08 Sep 14:20",
        updated: "08 Sep 15:10",
        actionLabel: "View",
      },
      {
        id: "rel-02",
        agentKey: "HR_POLICY_ADVISOR",
        agentName: "HR Policy Advisor",
        iconName: "users",
        iconColor: "#059669",
        iconBg: "#ecfdf5",
        version: "v0.1.0",
        requester: "HR Lead",
        status: "DRAFT",
        submitted: "06 Sep 10:12",
        updated: "08 Sep 10:12",
        actionLabel: "Continue",
      },
      {
        id: "rel-03",
        agentKey: "FINANCE_RECONCILIATION",
        agentName: "Finance Reconciliation",
        iconName: "database",
        iconColor: "#047857",
        iconBg: "#d1fae5",
        version: "v0.2.0",
        requester: "Finance Lead",
        status: "APPROVED",
        submitted: "07 Sep 11:20",
        updated: "07 Sep 16:40",
        actionLabel: "Release",
      },
      {
        id: "rel-04",
        agentKey: "DAILY_BRIEF",
        agentName: "Daily Brief",
        iconName: "file",
        iconColor: "#059669",
        iconBg: "#ecfdf5",
        version: "v0.1.0",
        requester: "Director",
        status: "RELEASED",
        submitted: "06 Sep 09:15",
        updated: "08 Sep 18:20",
        actionLabel: "Activate",
      },
      {
        id: "rel-05",
        agentKey: "EVIDENCE_CHECKER",
        agentName: "Evidence Checker",
        iconName: "shield",
        iconColor: "#0f766e",
        iconBg: "#ccfbf1",
        version: "v0.2.0",
        requester: "Property Lead",
        status: "RETURNED",
        submitted: "05 Sep 14:30",
        updated: "06 Sep 08:50",
        actionLabel: "View",
      },
      {
        id: "rel-06",
        agentKey: "RENTAL_CONTRACT_ANALYZER",
        agentName: "Rental Contract Analyzer",
        iconName: "file",
        iconColor: "#059669",
        iconBg: "#ecfdf5",
        version: "v0.1.0",
        requester: "Legal Lead",
        status: "IN_REVIEW",
        submitted: "05 Sep 11:10",
        updated: "06 Sep 14:22",
        actionLabel: "View",
      },
      {
        id: "rel-07",
        agentKey: "OCCUPANCY_INSIGHTS",
        agentName: "Occupancy Insights",
        iconName: "chart",
        iconColor: "#059669",
        iconBg: "#ecfdf5",
        version: "v0.1.0",
        requester: "Operations Lead",
        status: "APPROVED",
        submitted: "04 Sep 16:45",
        updated: "05 Sep 09:10",
        actionLabel: "Release",
      },
      {
        id: "rel-08",
        agentKey: "MAINTENANCE_COPILOT",
        agentName: "Maintenance Copilot",
        iconName: "settings",
        iconColor: "#047857",
        iconBg: "#d1fae5",
        version: "v0.3.0",
        requester: "Facilities Lead",
        status: "DRAFT",
        submitted: "03 Sep 09:20",
        updated: "04 Sep 12:18",
        actionLabel: "Continue",
      },
    ] as ReleaseRequestItem[],
    agentDirectory: [
      {
        id: "ag-dir-1",
        agentKey: "EVIDENCE_CHECKER",
        agentName: "Evidence Checker",
        purpose: "Detect, verify, and surface evidence for decisions.",
        iconName: "search_file",
        version: "v0.1.0",
        scope: "Property",
        risk: "LOW",
        status: "ACTIVE",
        lastRun: "09 Sep 2025 06:41",
        updated: "09 Sep 2025 06:50",
      },
      {
        id: "ag-dir-2",
        agentKey: "DAILY_BRIEF",
        agentName: "Daily Brief",
        purpose: "Generate daily executive brief.",
        iconName: "file",
        version: "v0.1.0",
        scope: "Company",
        risk: "LOW",
        status: "ACTIVE",
        lastRun: "09 Sep 2025 08:15",
        updated: "09 Sep 2025 09:12",
      },
      {
        id: "ag-dir-3",
        agentKey: "PERMIT_OVERDUE_MONITOR",
        agentName: "Permit Overdue Monitor",
        purpose: "Monitor and alert overdue permits.",
        iconName: "clock",
        version: "v0.1.0",
        scope: "Property",
        risk: "MEDIUM",
        status: "IN_REVIEW",
        lastRun: "08 Sep 2025 14:22",
        updated: "09 Sep 2025 10:03",
      },
      {
        id: "ag-dir-4",
        agentKey: "HR_POLICY_ADVISOR",
        agentName: "HR Policy Advisor",
        purpose: "Answer HR policy questions with company guidelines.",
        iconName: "users",
        version: "v0.1.0",
        scope: "HR",
        risk: "LOW",
        status: "DRAFT",
        lastRun: "--",
        updated: "09 Sep 2025 10:12",
      },
      {
        id: "ag-dir-5",
        agentKey: "FINANCE_RECONCILIATION",
        agentName: "Finance Reconciliation",
        purpose: "Reconcile finance data and flag anomalies.",
        iconName: "chart",
        version: "v0.1.0",
        scope: "Finance",
        risk: "HIGH",
        status: "SUSPENDED",
        lastRun: "07 Sep 2025 20:31",
        updated: "08 Sep 2025 23:40",
      },
    ] as AgentDirectoryItem[],
    testEvidence: [
      {
        id: "te-01",
        agentName: "Evidence Checker",
        agentKey: "EVIDENCE_CHECKER",
        category: "POSITIVE",
        testKey: "TC-001",
        expected: "SUCCESS",
        actual: "SUCCESS",
        status: "PASSED",
        lastRun: "09 Sep 06:41",
      },
      {
        id: "te-02",
        agentName: "Evidence Checker",
        agentKey: "EVIDENCE_CHECKER",
        category: "NEGATIVE",
        testKey: "TC-002",
        expected: "BLOCKED",
        actual: "BLOCKED",
        status: "PASSED",
        lastRun: "09 Sep 06:41",
      },
      {
        id: "te-03",
        agentName: "Evidence Checker",
        agentKey: "EVIDENCE_CHECKER",
        category: "REGRESSION",
        testKey: "TC-003",
        expected: "SUCCESS",
        actual: "SUCCESS",
        status: "PASSED",
        lastRun: "09 Sep 14:20",
      },
      {
        id: "te-04",
        agentName: "Evidence Checker",
        agentKey: "EVIDENCE_CHECKER",
        category: "SECURITY",
        testKey: "TC-004",
        expected: "BLOCKED",
        actual: "FAILED",
        status: "FAILED",
        lastRun: "09 Sep 14:20",
      },
      {
        id: "te-05",
        agentName: "Evidence Checker",
        agentKey: "EVIDENCE_CHECKER",
        category: "RECOVERY",
        testKey: "TC-005",
        expected: "SUCCESS",
        actual: "SUCCESS",
        status: "PASSED",
        lastRun: "08 Sep 12:20",
      },
      {
        id: "te-06",
        agentName: "Finance Reconciliation",
        agentKey: "FINANCE_RECONCILIATION",
        category: "POSITIVE",
        testKey: "TC-010",
        expected: "SUCCESS",
        actual: "SUCCESS",
        status: "PASSED",
        lastRun: "08 Sep 10:12",
      },
      {
        id: "te-07",
        agentName: "Finance Reconciliation",
        agentKey: "FINANCE_RECONCILIATION",
        category: "NEGATIVE",
        testKey: "TC-011",
        expected: "ERROR",
        actual: "BLOCKED",
        status: "BLOCKED",
        lastRun: "08 Sep 10:12",
      },
      {
        id: "te-08",
        agentName: "Finance Reconciliation",
        agentKey: "FINANCE_RECONCILIATION",
        category: "REGRESSION",
        testKey: "TC-012",
        expected: "SUCCESS",
        actual: "NOT RUN",
        status: "NOT RUN",
        lastRun: "07 Sep 16:30",
      },
      {
        id: "te-09",
        agentName: "Finance Reconciliation",
        agentKey: "FINANCE_RECONCILIATION",
        category: "SECURITY",
        testKey: "TC-013",
        expected: "DETECTED",
        actual: "DETECTED",
        status: "PASSED",
        lastRun: "07 Sep 16:30",
      },
      {
        id: "te-10",
        agentName: "Finance Reconciliation",
        agentKey: "FINANCE_RECONCILIATION",
        category: "RECOVERY",
        testKey: "TC-014",
        expected: "SUCCESS",
        actual: "PENDING",
        status: "PENDING",
        lastRun: "07 Sep 14:20",
      },
    ] as TestEvidenceItem[],
  },
  permissionsList: [
    {
      id: "perm-1",
      agentName: "Evidence Checker",
      agentKey: "EVIDENCE_CHECKER",
      permission: "task.read",
      capability: "Task",
      accessMode: "Read",
      status: "APPROVED",
      approvedBy: "IT Admin",
      actionLabel: "View",
    },
    {
      id: "perm-2",
      agentName: "Evidence Checker",
      agentKey: "EVIDENCE_CHECKER",
      permission: "evidence.read",
      capability: "Evidence",
      accessMode: "Read",
      status: "APPROVED",
      approvedBy: "IT Admin",
      actionLabel: "View",
    },
    {
      id: "perm-3",
      agentName: "Evidence Checker",
      agentKey: "EVIDENCE_CHECKER",
      permission: "document.read",
      capability: "Document",
      accessMode: "Read",
      status: "PENDING",
      approvedBy: "IT Admin",
      actionLabel: "Review",
    },
    {
      id: "perm-4",
      agentName: "Daily Brief",
      agentKey: "DAILY_BRIEF",
      permission: "report.create",
      capability: "Report",
      accessMode: "Create",
      status: "APPROVED",
      approvedBy: "IT Admin",
      actionLabel: "View",
    },
    {
      id: "perm-5",
      agentName: "Permit Monitor",
      agentKey: "PERMIT_OVERDUE_MONITOR",
      permission: "project.read",
      capability: "Project",
      accessMode: "Read",
      status: "APPROVED",
      approvedBy: "IT Admin",
      actionLabel: "View",
    },
  ] as AgentPermissionItem[],
  runtimeMonitoringList: [
    {
      id: "run-01",
      runId: "run_0710b",
      agentName: "Evidence Checker",
      agentKey: "EVIDENCE_CHECKER",
      version: "0.1.0",
      status: "SUCCESS",
      tokens: "1,240",
      costUsd: "0.0004",
      latency: "1.2s",
      time: "09:41",
    },
    {
      id: "run-02",
      runId: "run_047c9",
      agentName: "Evidence Checker",
      agentKey: "EVIDENCE_CHECKER",
      version: "0.1.0",
      status: "FAILED",
      tokens: "980",
      costUsd: "0.0016",
      latency: "2.4s",
      time: "09:30",
    },
    {
      id: "run-03",
      runId: "run_876ad",
      agentName: "Daily Brief",
      agentKey: "DAILY_BRIEF",
      version: "0.1.0",
      status: "SUCCESS",
      tokens: "3,420",
      costUsd: "0.0031",
      latency: "4.1s",
      time: "08:15",
    },
    {
      id: "run-04",
      runId: "run_8f56d",
      agentName: "Permit Monitor",
      agentKey: "PERMIT_OVERDUE_MONITOR",
      version: "0.1.0",
      status: "BLOCKED",
      tokens: "--",
      costUsd: "--",
      latency: "--",
      time: "07:50",
    },
    {
      id: "run-05",
      runId: "run_970b3",
      agentName: "HR Advisor",
      agentKey: "HR_POLICY_ADVISOR",
      version: "0.1.0",
      status: "SUCCESS",
      tokens: "2,110",
      costUsd: "0.0037",
      latency: "3.2s",
      time: "06:12",
    },
  ] as RuntimeMonitoringItem[],
  budgetOverview: {
    percentage: 62,
    usedAmount: "$1,240.50",
    totalAmount: "$2,000.00",
    dailyLimits: {
      requestLimit: { used: "1,240", max: "10,000", percent: 12 },
      outputTokenLimit: { used: "650,000", max: "1,000,000", percent: 65 },
      costLimit: { used: "$1,240.50", max: "$2,000.00", percent: 62 },
    },
    alerts: [
      {
        id: "balert-1",
        type: "info",
        title: "Output token mencapai 65%",
        subtitle: "Limit harian hampir tercapai",
        timeAgo: "2 jam yang lalu",
      },
      {
        id: "balert-2",
        type: "warning",
        title: "4 runtime gagal",
        subtitle: "Periksa Test & Evidence",
        timeAgo: "4 jam yang lalu",
      },
      {
  id: "balert-3",
        type: "warning",
        title: "1 kill switch aktif",
        subtitle: "Tinjau rencana pemulihan",
        timeAgo: "1 hari yang lalu",
      },
    ],
  } as BudgetOverviewData,
  killSwitchSystem: {
    globalHalted: false,
    globalHaltReason: "",
    activeAgentsCount: 4,
    haltedAgentsCount: 1,
    openAnomaliesCount: 2,
    mttrMinutes: 14,
    agents: [
      {
        agentKey: "EVIDENCE_CHECKER",
        agentName: "Evidence Checker",
        scope: "Property & Construction",
        status: "OPERATIONAL",
        currentVersion: "v0.1.0",
        previousStableVersion: "v0.0.9",
        availableVersions: ["v0.1.0", "v0.0.9", "v0.0.8"],
        circuitState: "CLOSED",
      },
      {
        agentKey: "DAILY_BRIEF",
        agentName: "Daily Brief",
        scope: "Executive Office",
        status: "OPERATIONAL",
        currentVersion: "v0.1.0",
        previousStableVersion: "v0.0.8",
        availableVersions: ["v0.1.0", "v0.0.8"],
        circuitState: "CLOSED",
      },
      {
        agentKey: "PERMIT_OVERDUE_MONITOR",
        agentName: "Permit Overdue Monitor",
        scope: "Property & Legal",
        status: "OPERATIONAL",
        currentVersion: "v0.1.0",
        previousStableVersion: "v0.0.7",
        availableVersions: ["v0.1.0", "v0.0.7"],
        circuitState: "CLOSED",
      },
      {
        agentKey: "HR_POLICY_ADVISOR",
        agentName: "HR Policy Advisor",
        scope: "Human Resources",
        status: "OPERATIONAL",
        currentVersion: "v0.1.0",
        previousStableVersion: "v0.0.5",
        availableVersions: ["v0.1.0", "v0.0.5"],
        circuitState: "CLOSED",
      },
      {
        agentKey: "FINANCE_RECONCILIATION",
        agentName: "Finance Reconciliation",
        scope: "Finance & Accounting",
        status: "HALTED",
        currentVersion: "v0.2.0",
        previousStableVersion: "v0.1.2",
        availableVersions: ["v0.2.0", "v0.1.2", "v0.1.0"],
        circuitState: "OPEN",
        lastHaltedAt: "09 Sep 2025 21:10",
        haltReason: "Anomali latensi & deviasi agregat saldo keuangan",
        latencyAnomaly: "4.8s (Limit 1.5s)",
      },
    ],
    rollbackHistory: [
      {
        id: "rb-01",
        agentKey: "FINANCE_RECONCILIATION",
        agentName: "Finance Reconciliation",
        fromVersion: "v0.2.1-beta",
        toVersion: "v0.2.0",
        reason: "Rollback darurat: deviasi saldo agregat terdeteksi saat rekonsiliasi",
        executedBy: "IT Admin (Budi Santoso)",
        executedAt: "09 Sep 2025 21:15",
        status: "VERIFIED",
      },
      {
        id: "rb-02",
        agentKey: "EVIDENCE_CHECKER",
        agentName: "Evidence Checker",
        fromVersion: "v0.1.1-rc1",
        toVersion: "v0.1.0",
        reason: "Regression failure pada security invariant check TC-004",
        executedBy: "Direktur Utama",
        executedAt: "05 Sep 2025 14:02",
        status: "SUCCESS",
      },
      {
        id: "rb-03",
        agentKey: "PERMIT_OVERDUE_MONITOR",
        agentName: "Permit Overdue Monitor",
        fromVersion: "v0.0.8-patch",
        toVersion: "v0.0.7",
        reason: "Timeout spike koneksi OCR dokumen IMB",
        executedBy: "IT Admin (Budi Santoso)",
        executedAt: "28 Agu 2025 09:30",
        status: "VERIFIED",
      },
    ],
  } as KillSwitchSystemState,
  auditTrailFullList: [
    {
      id: "aud-01",
      hash: "sha256:7f49c0d12ae93...4b12",
      action: "KILL_SWITCH_ENGAGED",
      actionTitle: "Agent Kill Switch Diaktifkan",
      severity: "CRITICAL",
      actor: { name: "Direktur Utama", role: "Executive Director", kind: "HUMAN", avatar: "DU" },
      entityType: "AGENT",
      entityId: "FINANCE_RECONCILIATION",
      reason: "Isolasi darurat akibat deviasi kalkulasi pada modul rekonsiliasi keuangan.",
      occurredAt: "09 Sep 2025 21:10",
      metadata: {
        ipAddress: "192.168.1.104",
        correlationId: "corr-ks-9901",
        prevValue: "OPERATIONAL",
        newValue: "HALTED",
        signature: "ed25519:9f8e7d6c5b4a3...",
        details: "Triggered via Governance Console. Circuit breaker opened for safety isolation.",
      },
    },
    {
      id: "aud-02",
      hash: "sha256:e3b0c44298fc1...89a1",
      action: "AGENT_ROLLBACK_EXECUTED",
      actionTitle: "Rollback Versi Rilis Agen",
      severity: "WARNING",
      actor: { name: "Budi Santoso", role: "IT Admin Lead", kind: "HUMAN", avatar: "BS" },
      entityType: "AGENT",
      entityId: "FINANCE_RECONCILIATION",
      reason: "Rollback versi rilis dari v0.2.1-beta ke v0.2.0 setelah verifikasi hash.",
      occurredAt: "09 Sep 2025 21:15",
      metadata: {
        ipAddress: "192.168.1.112",
        correlationId: "corr-rb-4412",
        prevValue: "v0.2.1-beta",
        newValue: "v0.2.0",
        signature: "ed25519:1a2b3c4d5e6...",
        details: "Artifact checksum verified against immutable Genesis registry.",
      },
    },
    {
      id: "aud-03",
      hash: "sha256:9a8f12c334bb0...51d9",
      action: "BUDGET_CAP_MODIFIED",
      actionTitle: "Pembaruan Limit Budget AI",
      severity: "INFO",
      actor: { name: "Direktur Utama", role: "Executive Director", kind: "HUMAN", avatar: "DU" },
      entityType: "BUDGET",
      entityId: "GLOBAL_WORKSPACE",
      reason: "Penyesuaian batas biaya harian menjadi $2,000.00 untuk akselerasi operasional Q3.",
      occurredAt: "09 Sep 2025 10:00",
      metadata: {
        ipAddress: "192.168.1.104",
        correlationId: "corr-bg-1200",
        prevValue: "$1,500.00",
        newValue: "$2,000.00",
        signature: "ed25519:88aa77bb66...",
        details: "Approved in Board Operations Meeting. Daily request cap set to 10,000.",
      },
    },
    {
      id: "aud-04",
      hash: "sha256:11a2b3c4d5e6f...88bc",
      action: "PERMISSION_POLICY_APPROVED",
      actionTitle: "Persetujuan Hak Akses Agen",
      severity: "SUCCESS",
      actor: { name: "Budi Santoso", role: "IT Admin Lead", kind: "HUMAN", avatar: "BS" },
      entityType: "PERMISSION",
      entityId: "EVIDENCE_CHECKER",
      reason: "Pemberian izin akses 'task.read' dan 'evidence.read' untuk keperluan verifikasi.",
      occurredAt: "09 Sep 2025 08:30",
      metadata: {
        ipAddress: "192.168.1.112",
        correlationId: "corr-pm-0782",
        prevValue: "PENDING",
        newValue: "APPROVED",
        signature: "ed25519:33cc44dd55...",
        details: "Capabilities bounded by Read-Only scoping on Property project data.",
      },
    },
    {
      id: "aud-05",
      hash: "sha256:88bc45d67e8f9...32fe",
      action: "RUNTIME_ANOMALY_BLOCKED",
      actionTitle: "Eksekusi Diblokir Safety Policy",
      severity: "WARNING",
      actor: { name: "Circuit Breaker Daemon", role: "ALOS Core Engine", kind: "SYSTEM", avatar: "CB" },
      entityType: "RUNTIME",
      entityId: "PERMIT_OVERDUE_MONITOR",
      reason: "Eksekusi run_8f56d diblokir otomatis oleh invariant safety rules (Token burst attempt).",
      occurredAt: "09 Sep 2025 07:50",
      metadata: {
        ipAddress: "10.0.0.1 (Internal Mesh)",
        correlationId: "corr-rt-8f56d",
        prevValue: "IN_PROGRESS",
        newValue: "BLOCKED",
        signature: "ed25519:55ee66ff77...",
        details: "Safety Invariant #2 violated: Single request exceeded 3,000 output tokens.",
      },
    },
    {
      id: "aud-06",
      hash: "sha256:45c6d7e8f9a0b...99ca",
      action: "AGENT_RELEASE_APPROVED",
      actionTitle: "Persetujuan Rilis Agen ke Produksi",
      severity: "SUCCESS",
      actor: { name: "Direktur Utama", role: "Executive Director", kind: "HUMAN", avatar: "DU" },
      entityType: "AGENT",
      entityId: "DAILY_BRIEF",
      reason: "Persetujuan rilis produksi versi v0.1.0 setelah seluruh test suite lolos 100%.",
      occurredAt: "08 Sep 2025 18:20",
      metadata: {
        ipAddress: "192.168.1.104",
        correlationId: "corr-rel-04",
        prevValue: "IN_REVIEW",
        newValue: "RELEASED",
        signature: "ed25519:77aa88bb99...",
        details: "Technical and Business reviews signed off with zero regression flags.",
      },
    },
    {
      id: "aud-07",
      hash: "sha256:34b5c6d7e8f9a...66db",
      action: "SECURITY_CONTRACT_VERIFIED",
      actionTitle: "Verifikasi Kontrak & SLA Agen",
      severity: "INFO",
      actor: { name: "Siti Rahma", role: "Compliance Lead", kind: "HUMAN", avatar: "SR" },
      entityType: "CONTRACT",
      entityId: "EVIDENCE_CHECKER",
      reason: "Verifikasi SLA respons latency 800ms dan proteksi data privasi dokumen proyek.",
      occurredAt: "08 Sep 2025 16:40",
      metadata: {
        ipAddress: "192.168.1.108",
        correlationId: "corr-ct-9921",
        prevValue: "DRAFT_CONTRACT",
        newValue: "VERIFIED_CONTRACT",
        signature: "ed25519:22bb33cc44...",
        details: "Model binding confirmed: gemini-1.5-flash with zero PII retention policy.",
      },
    },
    {
      id: "aud-08",
      hash: "sha256:56d7e8f9a0b1c...11ee",
      action: "TOKEN_LIMIT_WARNING",
      actionTitle: "Peringatan Ambang Batas Token",
      severity: "WARNING",
      actor: { name: "Telemetry Watcher", role: "ALOS Core Engine", kind: "SYSTEM", avatar: "TW" },
      entityType: "BUDGET",
      entityId: "GLOBAL_WORKSPACE",
      reason: "Penggunaan output token menembus ambang batas 65% (650,000 dari 1,000,000 token).",
      occurredAt: "08 Sep 2025 14:15",
      metadata: {
        ipAddress: "10.0.0.2 (Telemetry Agent)",
        correlationId: "corr-warn-65pct",
        prevValue: "NORMAL",
        newValue: "ELEVATED_USAGE",
        signature: "ed25519:44dd55ee66...",
        details: "Proactive alert dispatched to Executive Dashboard & Director bell notification.",
      },
    },
    {
      id: "aud-09",
      hash: "sha256:67e8f9a0b1c2d...77ff",
      action: "AGENT_REGISTERED",
      actionTitle: "Registrasi Agen Baru",
      severity: "INFO",
      actor: { name: "Hendra Wijaya", role: "Property Lead", kind: "HUMAN", avatar: "HW" },
      entityType: "AGENT",
      entityId: "PERMIT_OVERDUE_MONITOR",
      reason: "Pendaftaran registri agen baru untuk divisi Property & Construction.",
      occurredAt: "07 Sep 2025 11:20",
      metadata: {
        ipAddress: "192.168.1.115",
        correlationId: "corr-ag-reg-03",
        prevValue: "NEW",
        newValue: "DRAFT",
        signature: "ed25519:66ff77aa88...",
        details: "Initial agent scaffold created via Genesis Agent Designer with OCR capability.",
      },
    },
    {
      id: "aud-10",
      hash: "sha256:78f9a0b1c2d3e...8800",
      action: "LEDGER_ROOT_CHECKPOINT",
      actionTitle: "Merkle Root Ledger Checkpoint",
      severity: "SUCCESS",
      actor: { name: "Audit Anchor Daemon", role: "Security Subsystem", kind: "SYSTEM", avatar: "AD" },
      entityType: "GLOBAL_WORKSPACE",
      entityId: "GLOBAL_WORKSPACE",
      reason: "Merkle root ledger checkpoint terverifikasi konsisten dan tidak dapat diubah (immutable).",
      occurredAt: "07 Sep 2025 00:00",
      metadata: {
        ipAddress: "10.0.0.10 (Ledger Anchor)",
        correlationId: "corr-chkpt-20250907",
        prevValue: "BLOCK_#1044",
        newValue: "BLOCK_#1045",
        signature: "ed25519:88009911aa...",
        details: "Epoch checkpoint verified against distributed cryptographic timestamp authority.",
      },
    },
  ] as AuditTrailRecord[],
};
