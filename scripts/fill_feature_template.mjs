import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

// Run with the bundled artifact-tool runtime, from the project root.
const root = process.cwd();
const input = process.argv[2] ?? path.join(root,
  "docs/requirements/feature_split_reference.xlsx");
const output = process.argv[3] ?? path.join(root,
  "outputs/reports/feature_system_20261029/feature_split.xlsx");
const previewDir = process.argv[4] ?? path.join(root, ".cache/feature_split_review");
const source = JSON.parse(await fs.readFile(path.join(root,
  "outputs/reports/feature_system_20261029/feature_dictionary.json"), "utf8"));
const owners = {user:"用户", item:"商品", category:"类别", pair:"用户商品对",
  user_category:"用户类别", time:"时间", sequence:"行为序列"};
const definitions = Object.keys(owners).flatMap(owner =>
  source.features.filter(row => row.table === owner));
if (definitions.length !== 445 || new Set(definitions.map(row => row.name)).size !== 445)
  throw new Error("Actual feature dictionary is incomplete or duplicated");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const sheet = workbook.worksheets.getItem("Sheet1");
for (const address of ["E13:E14", "A2:A14", "A15:A24", "A25:A30", "A31:A35"])
  sheet.unmergeCells(address);
sheet.getRange("A2:E41").clear({applyTo:"contents"});

/** Preserve formula-looking descriptions as text.
 * @param {string} value Field definition text.
 * @returns {string} Literal spreadsheet value.
 */
function literal(value) {
  return value.startsWith("=") ? "'" + value : value;
}

const rows = definitions.map(row => {
  const window = row.window_days == null ? "按字段定义的历史范围或截点" :
    `截点前${row.window_days}天 [t-${row.window_days}天,t)`;
  const description = `${row.description}\n范围：${window}。` +
    `类型：${row.storage_dtype ?? row.dtype}。\n缺失：${row.missing_policy}。` +
    `\n状态：已生成，正式有效性筛选待完成。`;
  return [owners[row.table], row.name, row.chinese_name,
    row.calculation_explanation ?? row.calculation, description].map(literal);
});
sheet.getRange("A1:E1").values = [["所在表","特征名","特征","计算方法","特征描述"]];
sheet.getRange(`A2:E${rows.length + 1}`).values = rows;
const all = sheet.getRange(`A1:E${rows.length + 1}`);
all.format.font = {name:"Arial Unicode MS", size:11};
all.format.verticalAlignment = "top";
all.format.wrapText = true;
// Repeated table labels allow filtering 445 actual entries without merged cells.
const table = sheet.tables.add(`A1:E${rows.length + 1}`, true, "ConstructedFeatures");
table.style = "TableStyleLight9";
table.showFilterButton = true;
const header = sheet.getRange("A1:E1");
header.format.fill = "#1E3A50";
header.format.font = {name:"Arial Unicode MS", size:11, bold:true, color:"#FFFFFF"};
header.format.horizontalAlignment = "center";
header.format.verticalAlignment = "center";
header.format.rowHeight = 30;
[15, 48, 36, 68, 75].forEach((width, index) =>
  sheet.getRangeByIndexes(0,index,rows.length + 1,1).format.columnWidth = width);
rows.forEach((row,index) => {
  const lines = Math.max(...row.map((value,col) => value.split("\n").reduce(
    (count,line) => count + Math.max(1,Math.ceil(line.length / [8,40,18,42,38][col])),0)));
  sheet.getRange(`A${index + 2}:E${index + 2}`).format.rowHeight =
    Math.max(84, lines * 15 + 10);
});
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(2);
workbook.recalculate();
console.log((await workbook.inspect({kind:"table",range:"Sheet1!A1:E5",
  include:"values,formulas",maxChars:3000,tableMaxRows:5,tableMaxCols:5})).ndjson);
console.log((await workbook.inspect({kind:"match",
  searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options:{useRegex:true,maxResults:20},summary:"Formula error scan"})).ndjson);
await fs.mkdir(path.dirname(output), {recursive:true});
await fs.mkdir(previewDir, {recursive:true});
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(output);
for (const [label, range] of [["first", "A1:E5"], ["last", "A438:E446"]]) {
  const preview = await workbook.render({sheetName:"Sheet1",range,scale:1.3});
  await fs.writeFile(path.join(previewDir,`${label}.png`),
    new Uint8Array(await preview.arrayBuffer()));
}
console.log(JSON.stringify({output,rows:definitions.length, scalar:439, sequence:6}));
