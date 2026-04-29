"""Generate a sample PDF for testing the PDF agent.

We use a fictional but plausible technical report so that:
  * Evaluators can verify factual answers without external knowledge
  * Out-of-scope questions are obviously out-of-scope
  * Numeric / structured facts make hallucination easy to detect
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample.pdf"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


PAGES = [
    # Page 1
    """ACME Robotics — Annual Field Performance Report 2025

1. Executive Summary

This report summarises the field performance of the ACME R-7 autonomous
warehouse robot across 14 customer deployments during fiscal year 2025
(April 2024 – March 2025). The R-7 platform achieved an average uptime of
97.2% across all sites, with a mean time between failures (MTBF) of 4,820
operating hours. Total units shipped during the period: 1,284.

The most common failure mode was wheel-encoder drift, which accounted for
38% of all in-field service incidents. The second-most-common issue was
LiDAR window fogging in cold-storage deployments, at 21% of incidents.

Customer satisfaction, measured via the post-deployment NPS survey,
averaged 62 across all sites — an increase of 11 points compared to FY2024.
""",

    # Page 2
    """2. Product Overview

The R-7 is a 4-wheeled differential-drive autonomous mobile robot (AMR)
designed for indoor warehouse environments. Key specifications:

  - Payload capacity: 250 kg
  - Maximum speed: 2.0 m/s
  - Battery: 48V / 60Ah lithium iron phosphate
  - Charge time (0-80%): 38 minutes
  - Operating temperature: -10°C to +40°C
  - Localisation: 2D LiDAR (270° FOV) + wheel odometry + IMU
  - Onboard compute: NVIDIA Jetson Orin NX (16 GB)

The R-7 supports both centrally-orchestrated fleet operation via the ACME
Fleet Manager and standalone operation using on-board path planning.

2.1 Software Stack

The R-7 runs ACME OS 4.3 (Linux 6.1 kernel, real-time patched). Path
planning uses a hybrid A* planner with dynamic obstacle avoidance based on
the Timed Elastic Band local planner.
""",

    # Page 3
    """3. Deployment Statistics

3.1 Geographic Distribution

  - North America: 7 deployments (812 units)
  - Europe: 4 deployments (302 units)
  - Asia-Pacific: 3 deployments (170 units)

3.2 Industry Verticals

  - E-commerce fulfilment: 6 sites
  - Cold-chain logistics: 3 sites
  - Automotive parts distribution: 3 sites
  - Pharmaceutical: 2 sites

3.3 Largest Single Deployment

The largest single deployment is at Operator Logistics Inc., Memphis TN,
with 312 R-7 units in continuous operation across a 1.4 million square
foot fulfilment centre. This site achieved 98.6% uptime over the year.
""",

    # Page 4
    """4. Failure Mode Analysis

The 1,284 R-7 units logged 612 service incidents during FY2025. Breakdown:

  - Wheel-encoder drift: 233 incidents (38.1%)
  - LiDAR window fogging (cold-storage only): 129 incidents (21.1%)
  - Battery management system faults: 78 incidents (12.7%)
  - Drive motor brush wear: 54 incidents (8.8%)
  - Network connectivity drops: 47 incidents (7.7%)
  - Other / unclassified: 71 incidents (11.6%)

4.1 Wheel-Encoder Drift

Root cause: vibration-induced loosening of the encoder coupling in
high-traffic-density sites. Mitigation rolled out in firmware 4.3.2
(November 2024) reduced subsequent incidents by 64% in affected fleets.

4.2 LiDAR Fogging

Confined to cold-storage sites where temperature transitions cause
condensation. Hardware retrofit with a heated-window assembly began Q4
FY2025 and has been completed at 2 of 3 affected sites.
""",

    # Page 5
    """5. Financial Summary

Total revenue from R-7 sales and services in FY2025: USD 184.6 million,
broken down as:

  - Hardware sales: USD 132.1 million (71.5%)
  - Recurring software subscriptions: USD 31.4 million (17.0%)
  - Professional services and integration: USD 21.1 million (11.4%)

Gross margin on hardware was 34.2%; on software, 78.6%; on services, 22.0%.
Blended gross margin: 41.7%.

R&D spend during the period was USD 28.3 million (15.3% of revenue),
focused primarily on the upcoming R-8 platform and on perception-stack
improvements for cold-chain environments.
""",

    # Page 6
    """6. FY2026 Outlook

ACME projects FY2026 revenue in the range of USD 230–260 million, driven
by:

  - The R-8 platform launch, scheduled for Q3 FY2026
  - Expansion in the European cold-chain segment
  - A signed letter of intent with a major Australian retailer for a
    180-unit pilot starting July 2025

Key risks identified by management:

  - Continued lithium battery cell pricing volatility
  - Potential tariffs on imported semiconductor components
  - Talent retention in the perception engineering team

7. Closing Notes

This report was prepared by the ACME Field Reliability team and reviewed
by the Chief Technology Officer on 12 April 2025. All figures are
unaudited and subject to revision in the FY2025 audited financial
statements, expected June 2025.
""",
]


def build() -> Path:
    doc = fitz.open()
    for body in PAGES:
        page = doc.new_page()
        rect = fitz.Rect(54, 54, 558, 788)
        page.insert_textbox(
            rect,
            body,
            fontsize=11,
            fontname="helv",
            align=0,
        )
    doc.save(OUTPUT)
    doc.close()
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({path.stat().st_size} bytes)")
