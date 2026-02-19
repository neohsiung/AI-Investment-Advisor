# Security Policy

## Supported Versions

We actively provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 4.1.x   | ✅ Yes             |
| 4.0.x   | ✅ Yes             |
| < 4.0   | ❌ No              |

## Reporting a Vulnerability

We take the security of this project seriously. If you believe you have found a security vulnerability, please do **not** open a public issue. Instead, follow the process below:

1. **Email the Maintainer**: Send a detailed report to `supermfb@gmail.com`.
2. **Include Details**: Please include a description of the vulnerability, steps to reproduce, and potential impact.
3. **Response Timeline**: You can expect an acknowledgment within 48 hours. We will provide a timeline for a fix and keep you updated throughout the process.

## Our Commitment

This project adheres to strict security standards, including:
- **Zero-Tolerance for Hardcoded Secrets**: All credentials must be managed via environment variables.
- **Automated Scanning**: We use `bandit` and other static analysis tools in our CI/CD pipeline.
- **Dependency Auditing**: We regularly audit and pin dependencies to secure versions.

Thank you for helping keep the AI Investment Advisor community safe!
