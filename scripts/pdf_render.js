// 인쇄용 HTML → PDF (Playwright Chromium). 보통은 scripts/make_pdfs.sh로 실행한다.
// 사용: node scripts/pdf_render.js <jobs.json> <출력 폴더>
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch {
  console.error('Playwright를 찾지 못했어요. scripts/make_pdfs.sh로 실행하거나 안내에 따라 설치해 주세요.');
  process.exit(1);
}

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const outDir = process.argv[3];
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage();
  let failed = 0;
  for (const job of jobs) {
    await page.goto(pathToFileURL(job.html).href, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    const ok = await page.evaluate(() => document.fonts.check('12px KR', '가'));
    if (!ok) failed += 1;
    // 꼬리말에는 문서 글꼴이 적용되지 않아 시스템 고딕을 쓴다
    const footer = `<div style="width:100%;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:8px;color:#777;padding:0 14mm;display:flex;justify-content:space-between;">
      <span>제주 축제 메이커 · ${job.title}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`;
    await page.pdf({
      path: path.join(outDir, job.pdf),
      format: 'A4',
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate: footer,
    });
    console.log(`${job.pdf}: 한글 글꼴 ${ok ? '적용' : '실패'}`);
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
