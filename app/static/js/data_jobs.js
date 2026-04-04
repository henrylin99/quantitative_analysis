(function () {
    let currentRunId = null;
    let pollingTimer = null;
    let availableJobs = [];

    function showDataJobResult(message, type) {
        const box = document.getElementById("dataJobResult");
        if (!box) return;
        box.className = `alert alert-${type || "secondary"} mt-3 mb-0`;
        box.textContent = message;
    }

    function formatTime(text) {
        if (!text) return "-";
        try {
            return new Date(text).toLocaleString("zh-CN");
        } catch (error) {
            return text;
        }
    }

    function updateProgressView(run) {
        const badge = document.getElementById("dataJobProgressBadge");
        const progress = document.getElementById("dataJobProgress");
        const log = document.getElementById("dataJobRunLog");

        if (!badge || !progress || !log) return;

        if (!run) {
            badge.className = "badge bg-secondary";
            badge.textContent = "idle";
            progress.textContent = "暂无运行任务";
            log.textContent = "";
            return;
        }

        const status = run.status || "unknown";
        const badgeColor = {
            pending: "secondary",
            queued: "info",
            running: "primary",
            success: "success",
            failed: "danger",
            cancelled: "warning",
        }[status] || "secondary";

        badge.className = `badge bg-${badgeColor}`;
        badge.textContent = status;

        const percent = typeof run.progress === "number" ? `${run.progress.toFixed(1)}%` : "-";
        progress.textContent = `run_id=${run.id} | status=${status} | progress=${percent} | started=${formatTime(run.started_at)} | finished=${formatTime(run.finished_at)}`;

        const resultJson = run.result_json || {};
        const stdout = resultJson.stdout || "";
        const stderr = resultJson.stderr || "";
        const lines = [];
        if (stdout) lines.push(`[stdout]\n${stdout}`);
        if (stderr) lines.push(`[stderr]\n${stderr}`);
        if (!stdout && !stderr && run.error_message) lines.push(run.error_message);
        log.textContent = lines.join("\n\n");
    }

    function renderRunHistory(runs) {
        const container = document.getElementById("dataJobHistory");
        if (!container) return;

        if (!Array.isArray(runs) || runs.length === 0) {
            container.textContent = "暂无任务历史";
            return;
        }

        const rows = runs
            .map((run) => {
                const progress = typeof run.progress === "number" ? `${run.progress.toFixed(1)}%` : "-";
                return `<tr data-run-id="${run.id}">
                    <td>${run.id}</td>
                    <td>${run.job_type}</td>
                    <td>${run.status}</td>
                    <td>${progress}</td>
                    <td>${formatTime(run.finished_at || run.started_at || run.queued_at)}</td>
                </tr>`;
            })
            .join("");

        container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-sm table-hover mb-0">
                    <thead>
                        <tr>
                            <th>Run ID</th>
                            <th>任务</th>
                            <th>状态</th>
                            <th>进度</th>
                            <th>时间</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;

        container.querySelectorAll("tbody tr").forEach((row) => {
            row.addEventListener("click", function () {
                const runId = Number(this.getAttribute("data-run-id"));
                if (!Number.isNaN(runId) && runId > 0) {
                    currentRunId = runId;
                    fetchRunStatus(runId);
                    startPolling(runId);
                }
            });
        });
    }

    async function loadRunHistory() {
        try {
            const resp = await fetch("/api/data-jobs/list?limit=10");
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                return;
            }
            renderRunHistory(data.runs || []);
        } catch (error) {
            console.error("加载任务历史失败:", error);
        }
    }

    async function fetchRunStatus(runId) {
        try {
            const resp = await fetch(`/api/data-jobs/${runId}`);
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                showDataJobResult(`获取任务状态失败: ${data.error || "未知错误"}`, "warning");
                return null;
            }
            updateProgressView(data.run);
            return data.run;
        } catch (error) {
            console.error("获取任务状态失败:", error);
            return null;
        }
    }

    function stopPolling() {
        if (pollingTimer) {
            window.clearInterval(pollingTimer);
            pollingTimer = null;
        }
    }

    function startPolling(runId) {
        stopPolling();
        pollingTimer = window.setInterval(async function () {
            const run = await fetchRunStatus(runId);
            if (!run) return;
            if (["success", "failed", "cancelled"].includes(run.status)) {
                stopPolling();
                loadRunHistory();
            }
        }, 3000);
    }

    async function loadJobTypes() {
        const select = document.getElementById("jobTypeSelect");
        if (!select) return;

        try {
            const resp = await fetch("/api/data-jobs/jobs");
            const data = await resp.json();
            if (!data.success || !Array.isArray(data.jobs)) {
                return;
            }

            availableJobs = data.jobs.slice();
            select.innerHTML = "";
            data.jobs.forEach((job) => {
                const option = document.createElement("option");
                option.value = job.job_type;
                option.textContent = `${job.recommended_order || "-"} - ${job.display_name || job.job_type}`;
                select.appendChild(option);
            });
            updateSelectedJobMeta(select.value);
        } catch (error) {
            console.error("加载任务类型失败:", error);
        }
    }

    function updateSelectedJobMeta(jobType) {
        const job = availableJobs.find((item) => item.job_type === jobType);
        const displayName = document.getElementById("selectedJobDisplayName");
        const description = document.getElementById("selectedJobDescription");
        const group = document.getElementById("selectedJobGroup");
        const dependencies = document.getElementById("selectedJobDependencies");

        if (!displayName || !description || !group || !dependencies) return;

        if (!job) {
            displayName.textContent = "请选择任务";
            description.textContent = "任务描述会显示在这里。";
            group.textContent = "-";
            dependencies.textContent = "无";
            return;
        }

        displayName.textContent = job.display_name || job.job_type;
        description.textContent = job.description || "暂无任务说明。";
        group.textContent = job.group || "-";
        dependencies.textContent = Array.isArray(job.dependencies) && job.dependencies.length > 0
            ? job.dependencies.join(", ")
            : "无";
    }

    function bindRecommendedJobButtons() {
        const buttons = document.querySelectorAll("[data-recommended-job]");
        const select = document.getElementById("jobTypeSelect");

        if (!select || buttons.length === 0) {
            return;
        }

        buttons.forEach((button) => {
            button.addEventListener("click", function () {
                const jobType = this.getAttribute("data-recommended-job");
                if (!jobType) {
                    return;
                }
                select.value = jobType;
                updateSelectedJobMeta(jobType);
            });
        });
    }

    async function submitDataJob() {
        const select = document.getElementById("jobTypeSelect");
        const startDate = document.getElementById("jobStartDate")?.value;
        const endDate = document.getElementById("jobEndDate")?.value;

        if (!select || !select.value) {
            showDataJobResult("请选择任务类型", "warning");
            return;
        }

        showDataJobResult("任务提交中...", "info");

        try {
            const payload = {
                job_type: select.value,
                params: {
                    start_date: startDate || "",
                    end_date: endDate || "",
                },
            };
            const resp = await fetch("/api/data-jobs/submit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();

            if (!resp.ok || !data.success) {
                showDataJobResult(`任务提交失败: ${data.error || "未知错误"}`, "danger");
                return;
            }

            showDataJobResult(
                `任务提交成功: run_id=${data.run_id}, status=${data.status}`,
                "success"
            );
            currentRunId = data.run_id;
            await fetchRunStatus(currentRunId);
            startPolling(currentRunId);
            loadRunHistory();
        } catch (error) {
            console.error("提交任务失败:", error);
            showDataJobResult("任务提交失败，请检查服务状态", "danger");
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        const submitButton = document.getElementById("submitDataJobBtn");
        const refreshButton = document.getElementById("refreshDataJobHistoryBtn");

        if (submitButton) {
            submitButton.addEventListener("click", submitDataJob);
        }
        if (refreshButton) {
            refreshButton.addEventListener("click", loadRunHistory);
        }
        const jobTypeSelect = document.getElementById("jobTypeSelect");
        if (jobTypeSelect) {
            jobTypeSelect.addEventListener("change", function () {
                updateSelectedJobMeta(this.value);
            });
        }

        bindRecommendedJobButtons();
        updateProgressView(null);
        loadJobTypes();
        loadRunHistory();
    });
})();
