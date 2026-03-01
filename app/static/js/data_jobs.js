(function () {
    function showDataJobResult(message, type) {
        const box = document.getElementById("dataJobResult");
        if (!box) return;
        box.className = `alert alert-${type || "secondary"} mt-3 mb-0`;
        box.textContent = message;
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

            select.innerHTML = "";
            data.jobs.forEach((job) => {
                const option = document.createElement("option");
                option.value = job.job_type;
                option.textContent = `${job.group} - ${job.job_type}`;
                select.appendChild(option);
            });
        } catch (error) {
            console.error("加载任务类型失败:", error);
        }
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
        } catch (error) {
            console.error("提交任务失败:", error);
            showDataJobResult("任务提交失败，请检查服务状态", "danger");
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        const submitButton = document.getElementById("submitDataJobBtn");
        if (submitButton) {
            submitButton.addEventListener("click", submitDataJob);
        }
        loadJobTypes();
    });
})();
