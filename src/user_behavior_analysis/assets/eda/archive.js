"use strict";
/** GitHub Pages只读取完整数据预计算视图，不调用本机API。 */
window.dashboardArchive = (() => {
  let manifest;
  /** 读取发布清单并创建视图选择器。Returns: 默认日期与空类目选项。 */
  async function init() {
    const response = await fetch("./manifest.json");
    if (!response.ok) throw new Error("发布清单读取失败，请刷新或查看仓库Actions状态");
    manifest = await response.json();
    for (const id of ["start", "end", "cohort", "category"]) {
      document.getElementById(id).closest("label").hidden = true;
      document.getElementById(id).disabled = true;
    }
    const label = document.createElement("label");
    label.textContent = "已计算视图（日期 × 人群 × 类目）";
    const select = document.createElement("select");
    select.id = "savedView";
    manifest.views.forEach((view, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = view.label;
      select.append(option);
    });
    label.append(select);
    document.getElementById("controls").prepend(label);
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = `GitHub 在线版 · ${manifest.views.length}个全量计算视图。可切换图表、排名、关联目标并下载统计表。任意日期、人群、类目组合及商品下钻请使用本地版；在线版不重新查询原始记录。`;
    document.querySelector("header").append(note);
    document.getElementById("controls").querySelector("button").textContent = "加载视图";
    document.querySelector("footer").textContent = "本页来自已保存的完整数据聚合结果，未抽样。切换视图时全部核心模块同时更新；不支持的筛选和下钻未开放。";
    document.querySelectorAll("h3").forEach(heading => {
      heading.textContent = heading.textContent.replace("（点击下钻）", "");
    });
    return {start: manifest.views[0].filters.start, end: manifest.views[0].filters.end, categories: [], source_categories: manifest.source_categories};
  }
  /** 读取选定视图。Returns: 与本地API相同的聚合响应。Throws: 文件不可用时抛错。 */
  async function load() {
    const view = manifest.views[Number(document.getElementById("savedView").value)];
    const response = await fetch("./" + view.path);
    if (!response.ok) throw new Error("视图数据读取失败，请刷新重试");
    return response.json();
  }
  /** 转义CSV字段及文本公式。Args: value原始值。Returns: 引号包裹的CSV值。 */
  function cell(value) {
    let text = String(value ?? "");
    if (/^[=+@\-\t\r]/.test(text) && typeof value === "string") text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  /** 导出当前统计表。Args: data当前聚合；name白名单表名。 */
  function download(data, name) {
    const rows = data[name];
    if (!Array.isArray(rows) || !rows.length) {
      document.getElementById("status").textContent = "当前视图此表没有观测记录，可选择其他视图。";
      return;
    }
    const keys = Object.keys(rows[0]);
    const csv = [keys.map(cell).join(","), ...rows.map(row => keys.map(key => cell(row[key])).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], {type: "text/csv;charset=utf-8"}));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `eda_${name}_${data.filters.start}_${data.filters.end}_${data.filters.cohort}_${data.filters.category || "all"}.csv`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  /** 恢复全周期全部用户视图。 */
  function reset() { document.getElementById("savedView").value = "0"; }
  return {init, load, download, reset};
})();
