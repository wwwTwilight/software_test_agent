(function () {
  const uploadWrap = document.getElementById("upload-cases-wrap");
  const manualWrap = document.getElementById("manual-cases-wrap");
  const caseModeRadios = document.querySelectorAll("input[name='case_mode']");
  const addRowBtn = document.getElementById("add-row");
  const tableBody = document.querySelector("#manual-table tbody");
  const hiddenManualJson = document.getElementById("manual_cases_json");
  const form = document.getElementById("pipeline-form");
  const rowCount = document.getElementById("row-count");
  const runOverlay = document.getElementById("run-overlay");
  const runBtn = document.getElementById("run-btn");
  const overlayMessage = document.getElementById("overlay-message");
  const overlayStage = document.getElementById("overlay-stage");
  const overlaySteps = Array.from(document.querySelectorAll(".overlay-step"));
  const markdownSource = document.getElementById("markdown-source");
  const markdownRendered = document.getElementById("markdown-rendered");

  const overlayPhases = [
    {
      stage: "初始化",
      message: "正在校验输入并组装流水线...",
      active: "generate",
    },
    {
      stage: "生成用例",
      message: "模型正在生成黑盒与白盒测试用例...",
      active: "generate",
    },
    {
      stage: "执行测试",
      message: "正在运行测试程序并收集结果...",
      active: "run",
    },
    {
      stage: "生成报告",
      message: "正在汇总失败信息并产出分析报告...",
      active: "summary",
    },
  ];

  let overlayTimer = null;

  function refreshRowCount() {
    if (!tableBody || !rowCount) {
      return;
    }
    const count = tableBody.querySelectorAll("tr").length;
    rowCount.textContent = `当前 ${count} 条`;
  }

  function toggleCaseMode() {
    const selected = document.querySelector("input[name='case_mode']:checked");
    const mode = selected ? selected.value : "upload";
    if (mode === "manual") {
      uploadWrap.classList.add("hidden");
      manualWrap.classList.remove("hidden");
    } else {
      uploadWrap.classList.remove("hidden");
      manualWrap.classList.add("hidden");
    }
  }

  function addRow(defaults) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input class="case-id" value="${defaults?.id || ""}" /></td>
      <td><textarea class="case-input" rows="3">${defaults?.input || ""}</textarea></td>
      <td><textarea class="case-output" rows="3">${defaults?.output || ""}</textarea></td>
      <td><button type="button" class="btn btn-ghost remove-row">删</button></td>
    `;
    tableBody.appendChild(tr);
    refreshRowCount();
  }

  function collectManualRows() {
    const rows = Array.from(tableBody.querySelectorAll("tr"));
    return rows.map((row) => {
      const id = row.querySelector(".case-id")?.value || "";
      const input = row.querySelector(".case-input")?.value || "";
      const output = row.querySelector(".case-output")?.value || "";
      return { id, input, output };
    });
  }

  function setOverlayPhase(index) {
    if (!overlayMessage || !overlayStage || overlaySteps.length === 0) {
      return;
    }

    const phase = overlayPhases[index % overlayPhases.length];
    overlayMessage.textContent = phase.message;
    overlayStage.textContent = phase.stage;

    overlaySteps.forEach((step) => {
      step.classList.remove("is-active", "is-done");
      if (step.dataset.step === phase.active) {
        step.classList.add("is-active");
      }
    });

    const activeIndex = overlaySteps.findIndex((step) => step.dataset.step === phase.active);
    if (activeIndex >= 0) {
      overlaySteps.forEach((step, index) => {
        if (index < activeIndex) {
          step.classList.add("is-done");
        }
      });
    }
  }

  function startOverlayAnimation() {
    if (!runOverlay) {
      return;
    }

    if (overlayTimer) {
      window.clearInterval(overlayTimer);
    }

    let phaseIndex = 0;
    setOverlayPhase(phaseIndex);
    overlayTimer = window.setInterval(() => {
      phaseIndex = (phaseIndex + 1) % overlayPhases.length;
      setOverlayPhase(phaseIndex);
    }, 1350);
  }

  function renderMarkdownReport() {
    if (!markdownSource || !markdownRendered) {
      return;
    }

    const raw = (markdownSource.textContent || "").trim();
    if (!raw) {
      markdownRendered.textContent = "";
      return;
    }

    if (window.marked && typeof window.marked.parse === "function") {
      window.marked.setOptions({ gfm: true, breaks: true });
      const html = window.marked.parse(raw);
      if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
        markdownRendered.innerHTML = window.DOMPurify.sanitize(html);
      } else {
        markdownRendered.innerHTML = html;
      }
      return;
    }

    markdownRendered.textContent = raw;
  }

  caseModeRadios.forEach((radio) => {
    radio.addEventListener("change", toggleCaseMode);
  });

  if (addRowBtn) {
    addRowBtn.addEventListener("click", () => addRow({}));
  }

  if (tableBody) {
    tableBody.addEventListener("click", (e) => {
      const target = e.target;
      if (target instanceof HTMLElement && target.classList.contains("remove-row")) {
        const tr = target.closest("tr");
        if (tr) {
          tr.remove();
          refreshRowCount();
        }
      }
    });
  }

  if (form) {
    form.addEventListener("submit", () => {
      const selected = document.querySelector("input[name='case_mode']:checked");
      const mode = selected ? selected.value : "upload";
      if (mode === "manual" && hiddenManualJson) {
        hiddenManualJson.value = JSON.stringify(collectManualRows());
      }

      if (runOverlay) {
        runOverlay.classList.remove("hidden");
      }
      if (runBtn) {
        runBtn.disabled = true;
        runBtn.textContent = "运行中...";
      }
      startOverlayAnimation();
    });
  }

  toggleCaseMode();
  refreshRowCount();
  renderMarkdownReport();
})();
