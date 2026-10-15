const http = require('http');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

const PORT = process.env.PORT || 3000;
const DIST_DIR = path.join(__dirname, 'website', 'dist');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf'
};

const server = http.createServer((req, res) => {
  let reqUrl = decodeURI(req.url.split('?')[0]);
  if (reqUrl === '/') {
    reqUrl = '/index.html';
  }

  let filePath = path.join(DIST_DIR, reqUrl);

  // If path is a directory, look for index.html
  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, 'index.html');
  }

  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT') {
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(`<h1>404 页面未找到</h1><p>请求的文件不存在：${reqUrl}</p><p><a href="/">返回首页</a></p>`);
      } else {
        res.writeHead(500);
        res.end(`服务器错误: ${err.code}`);
      }
    } else {
      const ext = path.extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || 'application/octet-stream';
      res.writeHead(200, {
        'Content-Type': contentType,
        'Cache-Control': 'no-cache'
      });
      res.end(content);
    }
  });
});

function openBrowser(url) {
  const start = process.platform === 'darwin' ? 'open' :
                process.platform === 'win32' ? 'start' : 'xdg-open';
  exec(`${start} ${url}`);
}

server.listen(PORT, () => {
  const url = `http://localhost:${PORT}`;
  console.log('\n======================================================');
  console.log('🚀 JichangBuy 本地购买中心服务器已启动！');
  console.log(`📡 本地访问地址: \x1b[36m${url}\x1b[0m`);
  console.log(`📁 托管目录: ${DIST_DIR}`);
  console.log('======================================================\n');
  console.log('按 Ctrl + C 可终止服务器进程。\n');
  
  // 自动打开浏览器
  try {
    openBrowser(url);
  } catch (e) {
    // ignore
  }
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    const nextPort = Number(PORT) + 1;
    console.log(`端口 ${PORT} 已被占用，正在尝试端口 ${nextPort}...`);
    server.listen(nextPort);
  } else {
    console.error('服务器启动异常:', err);
  }
});
