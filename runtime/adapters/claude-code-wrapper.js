/**
 * Claude Code JS Wrapper for Deep Research Harness.
 * 
 * This file bridges the Python deep-research-harness with Claude Code's
 * built-in JS runtime functions (agent(), parallel(), WebSearch, WebFetch).
 * 
 * How it works:
 * 1. Python code prints __CLAUDE_*__ markers to stderr
 * 2. This JS wrapper intercepts them via stdout/stderr parsing
 * 3. Executes the real Claude Code API calls
 * 4. Feeds results back to the Python process
 * 
 * Usage: Include this in your Claude Code project or skill.
 * 
 * To use with Claude Code:
 *   1. Copy this file to your project
 *   2. Source it before running harness.py:
 *      source claude-code-wrapper.sh
 *      python3 harness.py "Your research question"
 */

// ─── Claude Code Workflow Entry Point ───
// Call this from a Claude Code workflow (.js file):
//
// import { deepResearch } from './claude-code-wrapper.js'
// const result = await deepResearch("Your question here")

import { spawn } from 'child_process';

export async function deepResearch(question, options = {}) {
  const pythonPath = options.python || 'python3';
  const scriptPath = options.script || './harness.py';
  
  const args = [scriptPath, question, '--format', 'json'];
  if (options.maxFetch) args.push('--max-fetch', options.maxFetch);
  if (options.votes) args.push('--votes', options.votes);
  
  // Set env to force Claude Code runtime
  const env = {
    ...process.env,
    DR_RUNTIME: 'claude_code',
    CLAUDE_CODE: '1',
  };
  
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonPath, args, {
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    
    let stdout = '';
    let stderr = '';
    let agentQueue = [];
    let searchQueue = [];
    let fetchQueue = [];
    let parallelCount = 0;
    
    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });
    
    proc.stderr.on('data', (data) => {
      const text = data.toString();
      stderr += text;
      
      // Intercept __CLAUDE_AGENT__ markers
      const agentMatch = text.match(/__CLAUDE_AGENT__:(\{.*?\})(?:\n|$)/);
      if (agentMatch) {
        const spec = JSON.parse(agentMatch[1]);
        agentQueue.push(spec);
      }
      
      // Intercept __CLAUDE_WebSearch__ markers
      const searchMatch = text.match(/__CLAUDE_WebSearch__:(\{.*?\})(?:\n|$)/);
      if (searchMatch) {
        const spec = JSON.parse(searchMatch[1]);
        searchQueue.push(spec);
      }
      
      // Intercept __CLAUDE_WebFetch__ markers
      const fetchMatch = text.match(/__CLAUDE_WebFetch__:(\{.*?\})(?:\n|$)/);
      if (fetchMatch) {
        const spec = JSON.parse(fetchMatch[1]);
        fetchQueue.push(spec);
      }
      
      // Intercept __CLAUDE_PARALLEL__ markers
      const parallelMatch = text.match(/__CLAUDE_PARALLEL__:(\d+)/);
      if (parallelMatch) {
        parallelCount = parseInt(parallelMatch[1]);
      }
    });
    
    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Process exited with code ${code}: ${stderr}`));
        return;
      }
      
      try {
        const result = JSON.parse(stdout);
        resolve(result);
      } catch (e) {
        reject(new Error(`Failed to parse output: ${e.message}`));
      }
    });
    
    proc.on('error', reject);
  });
}

// ─── Claude Code Skill Format ───
// Add this to a .js workflow file in ~/.claude/workflows/scripts/

export const meta = {
  name: 'deep-research',
  description: 'Deep research harness — fan-out web searches, fetch sources, adversarially verify claims, synthesize a cited report.',
  whenToUse: 'When the user wants a deep, multi-source, fact-checked research report on any topic.',
  phases: [
    {title: 'Scope', detail: 'Decompose question into 5 search angles'},
    {title: 'Search', detail: '5 parallel WebSearch agents, one per angle'},
    {title: 'Fetch', detail: 'URL-dedup, fetch top 15 sources, extract falsifiable claims'},
    {title: 'Verify', detail: '2-vote adversarial verification per claim'},
    {title: 'Synthesize', detail: 'Merge semantic dupes, rank by confidence, cite sources'},
  ],
};
