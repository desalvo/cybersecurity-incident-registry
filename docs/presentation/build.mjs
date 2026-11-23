// Compatibility launcher. CI uses the public Python generator directly.
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const project = path.resolve(args[0] && !args[0].startsWith('--') ? args.shift() : path.join(here, '../..'));
const python = process.env.CIR_PRESENTATION_PYTHON || 'python3';
const result = spawnSync(python, [path.join(project, 'scripts/build_training_presentation.py'),
  '--project-root', project, ...args], {stdio: 'inherit'});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
