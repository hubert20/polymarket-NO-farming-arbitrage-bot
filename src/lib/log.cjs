'use strict';

const prettyLogCli = require('console-fmt-cli');

function toBoolean(value, fallback) {
  if (value === undefined) return fallback;
  const normalized = String(value).trim().toLowerCase();
  if (normalized === 'true') return true;
  if (normalized === 'false') return false;
  return fallback;
}

const loggerOpts = {
  level: (process.env.LOG_LEVEL || 'info').trim().toLowerCase(),
  timestamps: toBoolean(process.env.LOG_TIMESTAMPS, false),
  color: toBoolean(process.env.LOG_COLOR, true),
  child: true,
};

const log = prettyLogCli.createLogger('nofarm', loggerOpts);

module.exports = { log, prettyLogCli };
