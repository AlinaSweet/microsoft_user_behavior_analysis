import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const report = path.join(root, "outputs/reports/feature_system_20261029");
const dictionary = JSON.parse(await fs.readFile(path.join(report,
  "feature_dictionary.json"), "utf8"));
const base = JSON.parse(await fs.readFile(path.join(root,
  "data/catalog/base_raw_v2.json"), "utf8"));
const latent = JSON.parse(await fs.readFile(path.join(report,
  "latent_fit.json"), "utf8"));
const names = {user:"用户", item:"商品", category:"类目", pair:"用户商品对",
  user_category:"用户类目", time:"时间", sequence:"序列输入"};
const features = dictionary.features;
const summary = dictionary.summary;
const workbook = Workbook.create();
const overview = workbook.worksheets.add("特征汇总");
const detail = workbook.worksheets.add("特征字典");
const lineage = workbook.worksheets.add("中间表依赖");
const quality = workbook.worksheets.add("质量与限制");
const navy = "#1E3A50";
const pale = "#EDF3F7";

/** Apply consistent readable spreadsheet typography.
 * @param {object} sheet Worksheet to format.
 * @param {string} address Populated or reserved range.
 * @returns {void}
 */
function base_format(sheet, address) {
  sheet.showGridLines = false;
  sheet.getRange(address).format.font = {name:"Arial Unicode MS", size:11};
  sheet.getRange(address).format.verticalAlignment = "center";
}

/** Add a title and a short scope line above a data table.
 * @param {object} sheet Target worksheet.
 * @param {string} last_column Last column letter.
 * @param {string} title Visible title.
 * @param {string} note Scope note.
 * @returns {void}
 */
function heading(sheet, last_column, title, note) {
  sheet.mergeCells("A1:" + last_column + "1");
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1:" + last_column + "1").format.font = {
    name:"Arial Unicode MS", size:16, bold:true, color:navy
  };
  sheet.getRange("A1:" + last_column + "1").format.rowHeight = 30;
  sheet.mergeCells("A2:" + last_column + "2");
  sheet.getRange("A2").values = [[note]];
  sheet.getRange("A2:" + last_column + "2").format.wrapText = true;
  sheet.getRange("A2:" + last_column + "2").format.rowHeight = 30;
}

/** Style one real header range without boxing all data cells.
 * @param {object} sheet Target worksheet.
 * @param {string} address Header row range.
 * @returns {void}
 */
function header(sheet, address) {
  const range = sheet.getRange(address);
  range.format.fill = navy;
  range.format.font = {name:"Arial Unicode MS", size:11,
    color:"#FFFFFF", bold:true};
  range.format.wrapText = true;
  range.format.rowHeight = 30;
}

/** Write a typed rectangular table and expose filters.
 * @param {object} sheet Target worksheet.
 * @param {Array} headers Column captions.
 * @param {Array} rows Typed data matrix.
 * @param {string} table_name Unique native Excel table name.
 * @returns {void}
 */
function write_table(sheet, headers, rows, table_name) {
  const end_row = rows.length + 4;
  const last = String.fromCharCode(64 + headers.length);
  sheet.getRange("A4:" + last + end_row).values = [headers, ...rows];
  const table = sheet.tables.add("A4:" + last + end_row, true, table_name);
  table.style = "TableStyleLight9";
  table.showFilterButton = true;
  header(sheet, "A4:" + last + "4");
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(2);
}

/** Keep formula-looking descriptions as literal text.
 * @param {unknown} value Value from the actual feature dictionary.
 * @returns {unknown} Safe typed cell value.
 */
function literal(value) {
  return typeof value === "string" && value.startsWith("=") ? "'" + value : value;
}

base_format(detail, "A1:N" + (features.length + 4));
heading(detail, "N", "全维度特征字典",
  "保留参考表前五列；窗口为截点前历史；文件中的 {anchor} 对应四个实际截点。");
const detail_rows = features.map(row => {
  const q = row.latest_quality;
  return [names[row.table], row.name, row.chinese_name, row.calculation_explanation ?? row.calculation,
    row.description, row.window_days ?? "n.a.", row.storage_dtype ?? row.dtype,
    row.missing_policy, row.status === "produced" ? "已产出" : "待产出",
    "data/processed/features_raw_v2/" + row.artifact,
    q?.missing_rate ?? "n.a.", q?.zero_rate ?? "n.a.",
    q ? (q.all_missing ? "全为空值" : q.constant_in_snapshot ? "当前截点常量" : "当前截点有变化") : "序列输入",
    row.preprocessing].map(literal);
});
write_table(detail,
  ["所在表","特征名","特征","计算方法","特征描述","窗口天数","存储类型",
   "缺失处理","产出状态","对应文件","最新空值率","最新零值率",
   "最新截点变化情况","后续预处理"],
  detail_rows, "FeatureDictionary");
const widths = [14,46,34,64,64,12,19,45,14,65,14,14,22,45];
widths.forEach((width,index) =>
  detail.getRangeByIndexes(0,index,features.length+4,1).format.columnWidth = width);
detail.getRange("A5:N" + (features.length+4)).format.wrapText = true;
features.forEach((row,index) => {
  const height = Math.min(140, Math.max(44, Math.ceil(Math.max(
    (row.calculation_explanation ?? row.calculation).length/64, row.description.length/30,
    row.missing_policy.length/23
  ))*15));
  detail.getRange("A" + (index+5) + ":N" + (index+5)).format.rowHeight = height;
});
detail.getRange("K5:L" + (features.length+4)).setNumberFormat("0.0%");
detail.getRange("F5:F" + (features.length+4)).setNumberFormat("0");

base_format(overview, "A1:H36");
heading(overview, "H", "用户行为特征构建",
  "完整有效记录口径；四个实际截点；候选特征尚待正式有效性筛选。");
const end = features.length + 4;
overview.getRange("A4").values = [["标量字段"]];
overview.getRange("B4").formulas = [[
  "=COUNTIFS('特征字典'!$A$5:$A$" + end + ",\"<>序列输入\","
  + "'特征字典'!$I$5:$I$" + end + ",\"已产出\")"
]];
overview.getRange("D4").values = [["逻辑序列输入"]];
overview.getRange("E4").formulas = [[
  "=COUNTIF('特征字典'!$A$5:$A$" + end + ",\"序列输入\")"
]];
overview.getRange("G4").values = [["字典条目"]];
overview.getRange("H4").formulas = [["=SUM(B4,E4)"]];
overview.getRange("B4").format.font = {name:"Arial Unicode MS",
  size:16, bold:true, color:"#B46137"};
overview.getRange("E4").format.font = {name:"Arial Unicode MS",
  size:16, bold:true, color:"#B46137"};
overview.getRange("H4").format.font = {name:"Arial Unicode MS",
  size:16, bold:true, color:"#B46137"};
overview.getRange("A6:C6").values = [["所在表","字段数","占字典条目"]];
header(overview,"A6:C6");
Object.values(names).forEach((label,index) => {
  const row = index + 7;
  overview.getRange("A"+row).values = [[label]];
  overview.getRange("B"+row).formulas = [[
    "=COUNTIF('特征字典'!$A$5:$A$" + end + ",A" + row + ")"
  ]];
  overview.getRange("C"+row).formulas = [["=B"+row+"/$H$4"]];
});
overview.getRange("C7:C13").setNumberFormat("0.0%");
overview.getRange("A16:H20").values = [
  ["截点","历史用户","历史商品","历史类目","候选快照行","标量列","30天实际覆盖","未来7天标签"],
  ...summary.snapshot_rows.map(row => [
    new Date(row.anchor+"T00:00:00Z"), row.users, row.items, row.categories,
    row.candidate_pairs, row.scalar_columns, row.history_coverage_30d,
    row.future_label_available ? "可观测" : "不可用"
  ])
];
header(overview,"A16:H16");
overview.getRange("A17:A20").setNumberFormat("yyyy-mm-dd");
overview.getRange("B17:G20").setNumberFormat("#,##0");
overview.mergeCells("A23:H23");
overview.getRange("A23").values = [["数量如何理解"]];
header(overview,"A23:H23");
overview.mergeCells("A24:H27");
overview.getRange("A24").values = [[
  summary.scalar_features + "个标量字段包含" + summary.svd_coordinate_columns + "个SVD坐标，坐标不再重复相加。"
  + "6类序列输入按逻辑字段统计。ID、标签、覆盖管理字段、"
  + "16个文件分片和4个重复截点均不计为新增特征。"
  + "四个截点共" + summary.candidate_snapshot_rows.toLocaleString("en-US")
  + "行，是带截点的候选快照行数，不能解释为不同用户商品组合总数。"
]];
overview.getRange("A24:H27").format.wrapText = true;
overview.getRange("A24:H27").format.fill = pale;
overview.mergeCells("A29:H29");
overview.getRange("A29").values = [["需要继续验证的质量限制"]];
header(overview,"A29:H29");
overview.getRange("A30:B31").values = [
  ["16维SVD解释方差", latent.explained_variance_sum],
  ["最新候选SVD可用比例", null]
];
const last_completion = JSON.parse(await fs.readFile(path.join(root,
  "data/processed/features_raw_v2/snapshots/2025-12-19/completion.json"),"utf8"));
overview.getRange("B31").values = [[
  last_completion.latent_coverage.available_candidate_pairs
  / last_completion.latent_coverage.candidate_pairs
]];
overview.getRange("B30:B31").setNumberFormat("0.00%");
overview.mergeCells("D30:H33");
overview.getRange("D30").values = [[
  "这些是实际产出的候选字段，数量不能代替有效性。"
  + "早期30天历史不足；新商品有未知词表标记；"
  + "共现规则仅覆盖有足够训练支持的788个商品。"
  + "没有金额，RF与购买次数均为代理，不能称完整金额型RFM。"
]];
overview.getRange("D30:H33").format.wrapText = true;
[23,16,16,16,21,14,20,23].forEach((width,index) =>
  overview.getRangeByIndexes(0,index,36,1).format.columnWidth = width);
overview.getRange("A17:H20").format.rowHeight = 27;

/** Resolve a stored artifact path relative to the repository.
 * @param {string} value Stored absolute data path.
 * @returns {string} Portable repository-relative path.
 */
const relative = value => path.relative(root, value);
const lineage_rows = [
  ["events","一个有效源记录","event_id",base.records.rows,
   "标准事件六列含源记录序号；原始业务值保留",
   "data/processed/base_raw_v2/events",
   "标准事实，供追溯与新版本校验","data/catalog/base_raw_v2.json"],
  ...base.tables.map(table => [table.name,
    table.name==="key_hour" ? "一个用户商品行为小时键" : "由主键确定的预计算行",
    table.keys.join(", "),table.rows,
    table.name==="key_hour" ? "raw_count保留出现次数" : "原始量与四元组量分别保存",
    relative(table.path),
    table.name==="user_hour_stats" ? "高频标记、小时序列与核对" : "后续历史窗口预计算",
    "data/catalog/base_raw_v2.json"])
];
base_format(lineage, "A1:H"+(lineage_rows.length+4));
heading(lineage,"H","中间表和特征表依赖",
  "中间表是有键、有行粒度的复用数据；正式特征按截点过滤历史后计算。");
write_table(lineage,["所在表","一行代表","键","实际行数","计数口径",
  "实际文件或目录","用途","清单位置"],lineage_rows,"IntermediateLineage");
[27,34,50,18,60,80,50,55].forEach((width,index) =>
  lineage.getRangeByIndexes(0,index,lineage_rows.length+4,1).format.columnWidth=width);
lineage.getRange("A5:H"+(lineage_rows.length+4)).format.wrapText=true;
lineage.getRange("A5:H"+(lineage_rows.length+4)).format.rowHeight=70;
lineage.getRange("D5:D"+(lineage_rows.length+4)).setNumberFormat("#,##0");

const quality_rows = features.filter(row=>row.latest_quality).map(row=>{
  const q=row.latest_quality;
  return [names[row.table],row.name,q.rows,q.missing_rate,q.zero_rate ?? "n.a.",
    q.minimum ?? "n.a.",q.maximum ?? "n.a.",
    q.all_missing?"全为空值":q.constant_in_snapshot?"当前截点常量":"有变化",q.invalid_values];
});
base_format(quality,"A1:I"+(quality_rows.length+4));
heading(quality,"I","最新截点字段质量",
  "2025-12-19；常量是该截点内的状态。空值率不等于错误率，分母为0的比率允许缺失。");
write_table(quality,["所在表","特征名","对应行数","空值率","零值率","最小值",
  "最大值","变化情况","非有限数数量"],quality_rows,"FeatureQuality");
[16,51,18,16,16,21,21,22,20].forEach((width,index)=>
  quality.getRangeByIndexes(0,index,quality_rows.length+4,1).format.columnWidth=width);
quality.getRange("C5:C"+(quality_rows.length+4)).setNumberFormat("#,##0");
quality.getRange("D5:E"+(quality_rows.length+4)).setNumberFormat("0.0%");
quality.getRange("F5:G"+(quality_rows.length+4)).setNumberFormat("#,##0.0000");
quality.getRange("A5:I"+(quality_rows.length+4)).format.rowHeight=27;

workbook.recalculate();
const inspected = await workbook.inspect({kind:"region",sheetId:"特征汇总",
  range:"A4:H13",maxChars:3500,tableMaxRows:10,tableMaxCols:8});
console.log(inspected.ndjson ?? inspected);
const image = await workbook.render({sheetName:"特征汇总",range:"A1:H33",
  scale:1.1,format:"png"});
await fs.writeFile(path.join(report,"feature_workbook_preview.png"),
  new Uint8Array(await image.arrayBuffer()));
for (const [sheetName, range, file] of [
  ["特征字典", "A1:E10", "feature_dictionary_preview.png"],
  ["质量与限制", "A1:I15", "feature_quality_preview.png"]
]) {
  const preview = await workbook.render({sheetName, range, scale:1.1,format:"png"});
  await fs.writeFile(path.join(report,file),
    new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(path.join(report,"feature_dictionary.xlsx"));
console.log(JSON.stringify({output:path.join(report,"feature_dictionary.xlsx"),
  scalar:summary.scalar_features,sequence:summary.sequence_fields,
  dictionary_rows:features.length}));
