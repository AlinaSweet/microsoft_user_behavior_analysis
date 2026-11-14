import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

// Usage: bundled Node export_current_dictionary.mjs <project-root> <preview-directory>
const root = process.argv[2];
const preview = process.argv[3];
const report = path.join(root, 'outputs/reports/stage2');
const data = JSON.parse(await fs.readFile(path.join(report, 'feature_dictionary.json'), 'utf8'));
const experiment = JSON.parse(await fs.readFile(path.join(report, 'encoding_experiments.json'), 'utf8'));
const wb = Workbook.create();
const definitions = wb.worksheets.add('特征定义与筛选');
const representation = wb.worksheets.add('预处理表示');
const matrix = wb.worksheets.add('矩阵列映射');
const evaluation = wb.worksheets.add('固定实验对照');
let tableCount = 0;
const palette = { navy: '#173F52', teal: '#227D88', pale: '#E8F1F4', muted: '#526772' };

/**
 * Write one documented, filterable table with its complete source records.
 * @param {object} sheet Destination worksheet.
 * @param {object} descriptor Title, source/interpretation note, and column headers.
 * @param {Array<Array>} rows All required records, never a truncated sample.
 * @param {Array<number>} widths Explicit column widths in pixels.
 */
function fillSheet(sheet, descriptor, rows, widths) {
  const { title, note, headers } = descriptor;
  const cols = headers.length;
  const extent = sheet.getRangeByIndexes(0, 0, rows.length + 5, cols);
  extent.format.font = { name: 'Arial Unicode MS', size: 11, color: '#243A46' };
  extent.format.verticalAlignment = 'center';
  sheet.showGridLines = false;
  sheet.tabColor = palette.teal;
  sheet.getRangeByIndexes(0, 0, 1, Math.min(3, cols)).merge();
  sheet.getRange('A1').values = [[title]];
  sheet.getRangeByIndexes(0, 0, 1, Math.min(3, cols)).format.fill = palette.navy;
  sheet.getRange('A1').format.font = { name: 'Arial Unicode MS', size: 20, bold: true, color: '#FFFFFF' };
  sheet.getRangeByIndexes(0, 0, 1, Math.min(3, cols)).format.rowHeightPx = 46;
  sheet.getRangeByIndexes(1, 0, 2, Math.min(4, cols)).merge();
  sheet.getRange('A2').values = [[note]];
  sheet.getRangeByIndexes(1, 0, 2, Math.min(4, cols)).format.wrapText = true;
  sheet.getRangeByIndexes(1, 0, 2, Math.min(4, cols)).format.fill = palette.pale;
  sheet.getRangeByIndexes(1, 0, 2, Math.min(4, cols)).format.rowHeightPx = 26;
  sheet.getRangeByIndexes(4, 0, 1, cols).values = [headers];
  sheet.getRangeByIndexes(5, 0, rows.length, cols).values = rows;
  sheet.getRangeByIndexes(4, 0, 1, cols).format.font = { name: 'Arial Unicode MS', size: 11, bold: true, color: '#FFFFFF' };
  sheet.getRangeByIndexes(4, 0, 1, cols).format.fill = palette.teal;
  sheet.getRangeByIndexes(4, 0, 1, cols).format.rowHeightPx = 32;
  sheet.getRangeByIndexes(5, 0, rows.length, cols).format.rowHeightPx = 72;
  sheet.getRangeByIndexes(5, 0, rows.length, cols).format.wrapText = true;
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, rows.length + 5, 1).format.columnWidthPx = width;
  });
  sheet.tables.add(sheet.getRangeByIndexes(4, 0, rows.length + 1, cols), true, `Data${++tableCount}`);
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(1);
}

const status = { selected: '保留', excluded: '排除本轮', deferred: '暂缓本轮', separate_sequence_input: '独立序列输入', produced: '已生成' };
const group = { basic: '基础统计', business: '业务转化', sequence: '序列统计', svd: '交互SVD', cooccurrence: '共现', calendar: '日历', sequence_array: '序列数组' };
const sourceRows = data.features.map(row => [
  row.name, row.chinese_name, row.table, row.family, group[row.current_group] ?? row.current_group,
  status[row.current_status] ?? row.current_status, row.business_protected ? '是' : '否',
  row.training_missing_rate ?? null, row.training_mi ?? null,
  row.current_preprocessing, row.decision_reason, row.calculation_explanation ?? row.calculation,
  row.description, row.window_days ?? null, row.dtype, row.artifact,
]);
fillSheet(definitions, {title: '微软商城｜当前特征字典',
  note: '445条源定义＝439标量＋6类序列；207标量进入本轮预实验。缺失率与互信息取训练期；空白表示未估计。来源：同目录feature_dictionary.json（2026-11-14）。',
  headers: ['字段名', '业务含义', '来源表', '特征族', '评估组', '本轮状态', '业务保护', '训练缺失率', '训练互信息', '当前预处理', '筛选原因', '计算口径', '适用边界', '天窗口', '类型', '原始产物']},
  sourceRows, [310, 260, 110, 120, 110, 130, 90, 110, 120, 340, 310, 460, 360, 90, 110, 400]);
definitions.getRange('H6:H450').setNumberFormat('0.00%');
definitions.getRange('I6:I450').setNumberFormat('0.000000');
definitions.getRange('N6:N450').setNumberFormat('0');

fillSheet(representation, {title: '预处理新增表示｜独立于445条源定义',
  note: '1个目标编码表示＋8个稀疏类别预嵌入坐标。仅训练拟合；推理不早于2025-12-02。embedding_all_known只用于覆盖管理，不进入矩阵。',
  headers: ['表示字段', '业务含义', '表示类别', '计算方法', '训练与推理规则', '用途及限制']},
  data.representations.map(r => [r.name, r.chinese_name, r.family, r.calculation, r.current_preprocessing, r.description]),
  [330, 300, 160, 460, 420, 460]);

const selected = data.features.filter(r => r.current_status === 'selected');
const matrixRows = data.matrix_column_names.map((name, index) => {
  const source = selected.find(r => name === r.name || name.startsWith(r.name + '__'));
  return [index, name, source?.name ?? (name.endsWith('__te') ? name.slice(0, -4) : '三类训练类别的联合投影'),
    name.startsWith('category_embedding_') ? '稀疏预嵌入' : name.endsWith('__te') ? '目标编码数值' : name.includes('__') ? '独热或缺失指示' : '数值标准化'];
});
fillSheet(matrix, {title: '最终矩阵列映射｜259列',
  note: '矩阵列数包括独热展开、缺失标记和8个投影坐标；不等于业务特征数量。三键与标签另存，避免标签进入模型输入。索引从0开始。',
  headers: ['列索引', '矩阵列名', '源字段或输入', '表示方式']}, matrixRows, [90, 500, 430, 240]);
matrix.getRange('A6:A264').setNumberFormat('0');
matrix.getRange('A6:D264').format.rowHeightPx = 42;

const val = experiment.evaluations.validation.metrics.all;
const test = experiment.evaluations.test.metrics.all;
fillSheet(evaluation, {title: '固定逻辑回归预实验｜相同完整候选行',
  note: '验证：2025-12-02；测试：2025-12-09。8组内按验证AP选择te_sequence；上一轮OHE序列组AP更高，不能宣布TE总体获胜。稀少正例、候选覆盖和短历史限制见README。',
  headers: ['输入组', '验证AUC', '验证AP', '测试AUC', '测试AP', '性质']},
  Object.keys(val).map(name => [name, val[name].roc_auc, val[name].average_precision, test[name].roc_auc, test[name].average_precision,
    ['basic','business'].includes(name) ? '已冻结OHE参考' : '本轮完整训练；测试不参与选择']),
  [220, 140, 140, 140, 140, 420]);
evaluation.getRange('B6:E13').setNumberFormat('0.00000');

wb.recalculate();
await fs.mkdir(preview, { recursive: true });
for (const [sheet, range] of [
  [definitions, 'A1:H10'], [representation, 'A1:D9'],
  [matrix, 'A1:D10'], [evaluation, 'A1:F13'],
]) {
  const rendered = await wb.render({ sheetName: sheet.name, range, scale: 1.1, format: 'png' });
  await fs.writeFile(path.join(preview, `${sheet.name}.png`), new Uint8Array(await rendered.arrayBuffer()));
}
for (const [sheet, range] of [[definitions,'A447:C450'],[definitions,'A225:C228'],[matrix,'A260:D264']]) {
  console.log((await wb.inspect({kind:'region', sheetId:sheet.name, range, maxChars:1800, tableMaxRows:5, tableMaxCols:4})).ndjson);
}
console.log((await wb.inspect({ kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#N/A|#NAME\\?', options:{useRegex:true,maxResults:10}, maxChars:1500 })).ndjson);
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(path.join(report, 'feature_dictionary.xlsx'));
console.log(JSON.stringify({sourceRows:sourceRows.length, representations:data.representations.length, matrixColumns:matrixRows.length, status:'exported'}));
