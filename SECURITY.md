# Security Policy

Security issues in Country Compare should be reported privately so they can be investigated and addressed before public disclosure.

## Supported versions

Security fixes are generally developed against the current `main` branch and released in the latest stable version of Country Compare.

Only the latest stable release is actively supported with security fixes. Older releases may not receive security updates.

## Reporting a vulnerability

**Do not open a public GitHub issue, discussion, or pull request containing details of a security vulnerability.**

Please use GitHub's private vulnerability reporting feature:

1. Open the repository's **Security** section.
2. Navigate to **Advisories**.
3. Select **Report a vulnerability**.
4. Submit the vulnerability details privately.

When reporting a vulnerability, include as much of the following information as possible:

* the affected component;
* the affected version or commit;
* a description of the vulnerability;
* steps to reproduce it;
* the potential security impact;
* relevant configuration or environment details;
* proof-of-concept information, if appropriate;
* any suggested mitigation or fix, if known.

Do not include real credentials, API keys, access tokens, or other third-party secrets in a report.

## Examples of security issues

Examples of issues that should be reported privately include:

* authentication or authorization bypasses;
* bypasses of API-key or service-token protection;
* unintended exposure of the private LLM forecast service;
* leakage of credentials or secrets through API responses, logs, containers, CI/CD, or configuration;
* vulnerabilities that allow unintended code execution, file access, or network access;
* security-sensitive injection vulnerabilities;
* exploitable dependency vulnerabilities that materially affect Country Compare;
* deployment or container configuration that unintentionally exposes protected functionality;
* vulnerabilities that allow unauthorized modification or disclosure of application data.

This list is not exhaustive.

## Responsible testing

When investigating a potential vulnerability:

* prefer testing against a local instance of Country Compare;
* do not access data or systems that you do not own or have permission to test;
* do not attempt to obtain real deployment credentials or provider secrets;
* do not intentionally disrupt the publicly deployed application;
* do not perform denial-of-service testing against public deployments;
* do not generate excessive traffic or costs against third-party services or LLM providers.

## Disclosure process

After a report is received, the vulnerability will be reviewed and additional information may be requested.

If the report is accepted as a security vulnerability, the goal is to investigate the impact, develop and validate a fix, and release an appropriate update before public disclosure.

Please allow reasonable time for investigation and remediation before publishing vulnerability details.

This project currently does not guarantee a specific response or remediation SLA.

## Security advisories

When appropriate, confirmed vulnerabilities may be handled using GitHub Repository Security Advisories so discussion and remediation can take place privately before an advisory is published.

## Bug bounty

Country Compare does not currently operate a paid bug bounty program.

Security reports and responsible disclosure are nevertheless appreciated.
