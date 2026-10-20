const next = require('next');
const app = next({ dev: false });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = require('http').createServer((req, res) => handle(req, res));
  server.listen(3200, () => console.log('OpsIQ Frontend ready on http://localhost:3200'));
});
