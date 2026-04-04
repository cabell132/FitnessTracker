#!/usr/bin/env node
/**
 * Hook script to lint Python files with ruff/ty and TypeScript files with eslint after edits
 * Cross-platform Node.js version
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Read JSON input from stdin
let jsonInput = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  jsonInput += chunk;
});

process.stdin.on('end', () => {
  try {
    const json = JSON.parse(jsonInput.trim());
    const filePath = json.file_path;

    if (!filePath) {
      process.exit(0);
    }

    // Normalize path separators
    const normalizedPath = filePath.replace(/\\/g, '/');

    // Get the workspace root
    const scriptDir = __dirname;
    const workspaceRoot = path.resolve(scriptDir, '..', '..');
    const backendDir = path.join(workspaceRoot, 'backend');
    const frontendDir = path.join(workspaceRoot, 'frontend');

    // Check if file is a Python file
    if (normalizedPath.match(/\.py$/)) {
      // Python file - check if it's in backend
      const pyprojectPath = path.join(backendDir, 'pyproject.toml');
      if (!fs.existsSync(pyprojectPath)) {
        process.exit(0);
      }

      // Check if the edited file is within the backend directory structure
      const backendPathNormalized = backendDir.replace(/\\/g, '/');
      const workspacePathNormalized = workspaceRoot.replace(/\\/g, '/');
      if (
        !normalizedPath.startsWith(backendPathNormalized) &&
        !normalizedPath.startsWith(`${workspacePathNormalized}/backend`)
      ) {
        process.exit(0);
      }

      // Get relative path from backend directory
      let relPath = normalizedPath.replace(backendPathNormalized + '/', '');
      relPath = relPath.replace(/^\//, '');

      // Run ruff check with --fix on the specific file
      console.error(`Running ruff check on ${relPath}...`);
      const ruffCheck = spawn('uv', ['run', 'ruff', 'check', relPath, '--fix'], {
        cwd: backendDir,
        stdio: 'inherit',
        shell: process.platform === 'win32',
      });

      ruffCheck.on('close', (code) => {
        // Run ruff format on the specific file
        console.error(`Running ruff format on ${relPath}...`);
        const ruffFormat = spawn('uv', ['run', 'ruff', 'format', relPath], {
          cwd: backendDir,
          stdio: 'inherit',
          shell: process.platform === 'win32',
        });

        ruffFormat.on('close', () => {
          // Run ty check (checks whole project, but that's fine)
          // Only run if the file is in the src directories configured in ty.toml
          if (
            relPath.startsWith('tunetrove_backend/') ||
            relPath.startsWith('tests/')
          ) {
            console.error('Running ty check...');
            const tyCheck = spawn('uv', ['run', 'ty', 'check'], {
              cwd: backendDir,
              stdio: ['inherit', 'pipe', 'inherit'],
              shell: process.platform === 'win32',
            });

            let output = '';
            tyCheck.stdout?.on('data', (data) => {
              output += data.toString();
            });

            tyCheck.on('close', () => {
              // Limit output to first 50 lines
              const lines = output.split('\n').slice(0, 50);
              console.error(lines.join('\n'));
              process.exit(0);
            });
          } else {
            process.exit(0);
          }
        });
      });

      // Check if file is a TypeScript file
    } else if (normalizedPath.match(/\.(ts|tsx)$/)) {
      // TypeScript file - check if it's in frontend
      const packageJsonPath = path.join(frontendDir, 'package.json');
      if (!fs.existsSync(packageJsonPath)) {
        process.exit(0);
      }

      // Check if the edited file is within the frontend directory structure
      const frontendPathNormalized = frontendDir.replace(/\\/g, '/');
      const workspacePathNormalized = workspaceRoot.replace(/\\/g, '/');
      if (
        !normalizedPath.startsWith(frontendPathNormalized) &&
        !normalizedPath.startsWith(`${workspacePathNormalized}/frontend`)
      ) {
        process.exit(0);
      }

      // Get relative path from frontend directory
      let relPath = normalizedPath.replace(frontendPathNormalized + '/', '');
      relPath = relPath.replace(/^\//, '');

      // Run eslint on the specific file with --fix for auto-fixing
      console.error(`Running eslint on ${relPath}...`);
      const eslint = spawn('npx', ['eslint', relPath, '--fix'], {
        cwd: frontendDir,
        stdio: 'inherit',
        shell: process.platform === 'win32',
      });

      eslint.on('close', () => {
        process.exit(0);
      });
    } else {
      // Not a supported file type, exit silently
      process.exit(0);
    }
  } catch (error) {
    // If JSON parsing fails, exit silently
    process.exit(0);
  }
});
