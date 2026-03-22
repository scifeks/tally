## Glossary

**Authentication**
The process of verifying that a user, system, or service is who or what it
claims to be.  Weak authentication — such as guessable passwords or missing
multi-factor requirements — is one of the most common root causes of security
incidents.

**Authorization**
The process of determining what an authenticated identity is permitted to do.
An authorization failure occurs when a user can access resources or perform
actions beyond their intended privileges (see also: IDOR).

**CVSS**
Common Vulnerability Scoring System.  An open industry standard for rating the
severity of security vulnerabilities on a numeric scale from 0.0 to 10.0.
This report uses CVSS version 3.1.

**CWE**
Common Weakness Enumeration.  A community-maintained catalogue of software and
hardware weaknesses maintained by MITRE.  CWE identifiers (e.g. CWE-89) allow
vulnerabilities to be mapped to a root-cause category.

**DAST**
Dynamic Application Security Testing.  Automated analysis of a running
application from the outside — typically by sending crafted HTTP requests —
to identify vulnerabilities without access to source code.

**Dependency**
A third-party library or package included in an application.  Vulnerable
dependencies are a common attack vector because a single outdated package can
expose an otherwise secure application to known exploits.

**IDOR**
Insecure Direct Object Reference.  An authorization vulnerability where an
application exposes internal identifiers (e.g. database IDs) in URLs or
parameters and does not verify that the requesting user is entitled to access
the referenced object.

**Remediation**
The action taken to resolve a vulnerability or weakness.  This report includes
recommended remediation steps for each finding to guide the development team
in addressing identified issues.

**SAST**
Static Application Security Testing.  Automated analysis of source code or
compiled binaries to identify security flaws without executing the application.
SAST tools are particularly effective at detecting injection flaws, insecure
API usage, and hard-coded credentials.

**Secrets**
Sensitive values embedded in code or configuration files, such as API keys,
passwords, private keys, or access tokens.  Exposed secrets can allow an
attacker to authenticate as the application or access third-party services
without authorisation.

**SCA**
Software Composition Analysis.  Automated scanning of third-party dependencies
to identify packages with known vulnerabilities, licence issues, or outdated
versions.

**Severity**
A rating that indicates the potential impact and exploitability of a finding.
See the Severity Definitions section for the specific tiers and CVSS ranges
used in this report.

**Triage**
The process of reviewing automated findings to confirm whether they are genuine
vulnerabilities, assess their real-world impact, and assign a final severity
rating.  Triaged findings reflect human review and are more reliable than
raw automated output.

**Vulnerability**
A specific, exploitable flaw in a system, application, or configuration that
could be leveraged by an attacker to cause harm.  Unlike a weakness, a
vulnerability has a concrete attack vector and measurable impact.

**WAF**
Web Application Firewall.  A security control that filters and monitors HTTP
traffic between a web application and the internet.  A WAF can mitigate certain
attacks in production but is not a substitute for fixing underlying
vulnerabilities in the application code.

**Weakness**
A flaw in design, implementation, or configuration that could become a
vulnerability under the right conditions, but does not necessarily have a
direct exploit path.  Weaknesses are typically lower-severity findings that
represent deviations from security best practice.
