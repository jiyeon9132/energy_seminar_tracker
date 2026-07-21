const https = require('https');

function esc(s) {
  return (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, ' ').trim();
}

function httpRequest(urlStr, options = {}, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const opts = {
      hostname: url.hostname,
      path: url.pathname + url.search,
      method: options.method || 'GET',
      headers: options.headers || {},
    };
    const req = https.request(opts, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch (e) { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

async function crawlUrl(url) {
  const FC_KEY = process.env.FIRECRAWL_API_KEY;
  const bodyStr = JSON.stringify({ url, formats: ['markdown'] });
  const res = await httpRequest('https://api.firecrawl.dev/v1/scrape', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${FC_KEY}`,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(bodyStr),
    },
  }, bodyStr);
  if (res.status === 403) throw new Error('FORBIDDEN');
  if (res.status !== 200) throw new Error(`CRAWL_FAIL:${res.status}`);
  return res.body?.data?.markdown || '';
}

function parseEvent(markdown, sourceUrl) {
  const lines = markdown.split('\n').map(l => l.trim()).filter(Boolean);
  const text = lines.join(' ');

  // 제목
  let title = '';
  for (const line of lines) {
    if (line.startsWith('#')) { title = line.replace(/^#+\s*/, '').trim(); break; }
  }
  if (!title) {
    const bold = markdown.match(/\*\*([^*]{10,80})\*\*/);
    if (bold) title = bold[1].trim();
  }
  if (!title) title = lines[0]?.slice(0, 60) || '';

  // 날짜
  let date = '';
  const datePatterns = [
    /202[6-9][.\s년]\s*(\d{1,2})[.\s월]\s*(\d{1,2})/,
    /(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/,
    /(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/,
  ];
  for (const pat of datePatterns) {
    const m = text.match(pat);
    if (m) { date = m[0].replace(/\s+/g, ''); break; }
  }

  // 시간
  let time = '';
  const timeMatch = text.match(/(\d{1,2})[시:]\s*(\d{2})분?/);
  if (timeMatch) time = `${timeMatch[1]}:${timeMatch[2]}`;

  const displayDate = date
    ? (time ? `${date} ${time}` : date)
    : '미정';

  // 장소
  let venue = '';
  const venuePatterns = [
    /장소\s*[:：]\s*([^\n,]{5,40})/,
    /위치\s*[:：]\s*([^\n,]{5,40})/,
    /(국회의원회관|프레스센터|코엑스|벡스코|킨텍스|전경련회관|FKI타워|세종청사|정부청사)/,
  ];
  for (const pat of venuePatterns) {
    const m = text.match(pat);
    if (m) { venue = (m[1] || m[0]).trim().slice(0, 40); break; }
  }

  // 주관
  let org = '';
  const orgPatterns = [
    /주관\s*[:：]\s*([^\n,]{3,30})/,
    /주최\s*[:：]\s*([^\n,]{3,30})/,
    /주관기관\s*[:：]\s*([^\n,]{3,30})/,
  ];
  for (const pat of orgPatterns) {
    const m = text.match(pat);
    if (m) { org = m[1].trim().slice(0, 30); break; }
  }

  // 월
  let month = new Date().getMonth() + 1;
  const mMatch = text.match(/202[6-9][.\s년]\s*(\d{1,2})/);
  if (mMatch) month = parseInt(mMatch[1]);

  // 파싱 품질 점수 (제목+날짜+장소+주관 중 몇 개 파싱됐는지)
  const score = [title, date, venue, org].filter(Boolean).length;

  return { title, date: displayDate, org: org || '미정', venue: venue || '미정', month, url: sourceUrl, score };
}

async function ghGetFile(path) {
  const GH_TOKEN = process.env.GH_TOKEN;
  const REPO = process.env.REPO_NAME;
  const res = await httpRequest(
    `https://api.github.com/repos/${REPO}/contents/${path}`,
    { headers: { Authorization: `token ${GH_TOKEN}`, Accept: 'application/vnd.github.v3+json', 'User-Agent': 'energy-seminar-bot' } }
  );
  if (res.status === 404) return { content: '', sha: '' };
  const content = Buffer.from(res.body.content, 'base64').toString('utf-8');
  return { content, sha: res.body.sha };
}

async function ghPutFile(path, content, sha, message) {
  const GH_TOKEN = process.env.GH_TOKEN;
  const REPO = process.env.REPO_NAME;
  const encoded = Buffer.from(content, 'utf-8').toString('base64');
  const bodyStr = JSON.stringify({ message, content: encoded, ...(sha ? { sha } : {}) });
  const res = await httpRequest(
    `https://api.github.com/repos/${REPO}/contents/${path}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `token ${GH_TOKEN}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(bodyStr),
        'User-Agent': 'energy-seminar-bot',
      },
    },
    bodyStr
  );
  return res.status === 200 || res.status === 201;
}

async function addToHtml(event) {
  const { content: html, sha } = await ghGetFile('index.html');
  if (!html) throw new Error('index.html 읽기 실패');

  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '.');
  const month = event.month;
  const dVar = `D${month}`;

  const newEntry = `  {title:"${esc(event.title)}",status:"일정확정",prio:"우선",day:null,date:"${esc(event.date)}",org:"${esc(event.org)}",venue:"${esc(event.venue)}",cost:"미정",content:"",speakers:"미정",src:"URL 직접 등록 (${today})",url:"${esc(event.url)}"}`;

  let updated = html;
  if (updated.includes(`const ${dVar}=[`)) {
    updated = updated.replace(
      new RegExp(`(const ${dVar}=\\[)([\\s\\S]*?)(\\];)`),
      (_, open, body, close) => {
        const trimmed = body.trimEnd();
        const sep = trimmed.trim() ? ',\n' : '\n';
        return `${open}${trimmed}${sep}${newEntry}\n${close}`;
      }
    );
  } else {
    const newArray = `const ${dVar}=[\n${newEntry}\n];\n\n`;
    updated = updated.replace('const DATA_MAP =', newArray + 'const DATA_MAP =');
    updated = updated.replace(
      /(const DATA_MAP\s*=\s*\{)([^}]+)(\};)/,
      (_, open, body, close) => `${open}${body}, ${month}: ${dVar}${close}`
    );
  }

  const ok = await ghPutFile('index.html', updated, sha,
    `[URL등록] ${month}월 행사: ${event.title.slice(0, 30)}`);
  if (!ok) throw new Error('GitHub 업데이트 실패');
}

async function sendTelegram(text) {
  const TG_TOKEN = process.env.TELEGRAM_TOKEN;
  const TG_CHANNEL = process.env.TELEGRAM_CHANNEL_ID;
  if (!TG_TOKEN || !TG_CHANNEL) return;
  const bodyStr = JSON.stringify({ chat_id: TG_CHANNEL, text });
  await httpRequest(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(bodyStr) },
  }, bodyStr).catch(() => {});
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST만 허용' });

  let body = '';
  await new Promise(resolve => { req.on('data', c => body += c); req.on('end', resolve); });

  let url;
  try { url = JSON.parse(body).url; } catch (e) {}
  if (!url) return res.status(400).json({ error: 'URL이 필요합니다' });

  try {
    const markdown = await crawlUrl(url);
    if (!markdown) throw new Error('CRAWL_FAIL:EMPTY');

    const event = parseEvent(markdown, url);

    // 파싱 품질이 낮으면 수기입력 안내
    // score: 제목+날짜+장소+주관 중 파싱된 항목 수 (최대 4)
    if (event.score < 2) {
      return res.status(422).json({
        error: 'PARSE_FAIL',
        message: '페이지에서 행사 정보를 자동으로 읽을 수 없습니다.',
        suggestion: '수기입력을 이용해 주세요.',
        parsedTitle: event.title || '',
      });
    }

    await addToHtml(event);

    const DASHBOARD_URL = process.env.DASHBOARD_URL || 'https://energy-seminar.vercel.app';
    await sendTelegram(
      `[행사 등록 알림] URL 자동 등록\n\n` +
      `행사명: ${event.title}\n` +
      `일시: ${event.date}\n` +
      `주관: ${event.org}\n` +
      `장소: ${event.venue}\n\n` +
      `대시보드: ${DASHBOARD_URL}`
    );

    return res.status(200).json({ success: true, event });

  } catch (err) {
    // 크롤링 차단 또는 접근 불가
    if (err.message === 'FORBIDDEN' || err.message?.startsWith('CRAWL_FAIL')) {
      return res.status(422).json({
        error: 'CRAWL_FAIL',
        message: '해당 페이지에 접근할 수 없습니다.',
        suggestion: '수기입력을 이용해 주세요.',
      });
    }
    return res.status(500).json({ error: err.message || '서버 오류' });
  }
};
