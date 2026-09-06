const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const target = path.join(root, 'app', 'static', 'vendor');
fs.mkdirSync(target, {recursive: true});
for (const [source, name] of [['dist/shaka-player.compiled.js', 'shaka-player.js'], ['LICENSE', 'shaka-player.LICENSE']]) {
  fs.copyFileSync(path.join(root, 'node_modules', 'shaka-player', source), path.join(target, name));
}
