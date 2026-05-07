# 고객사 CSR 요구사항 요약 (현대·기아 / GM / 공통)

## 핵심 요약
국내 완성차 업체(현대·기아차, 한국GM)는 AIAG & VDA FMEA 1st Edition(2019)을 기본 요구하며
추가 요구사항을 CSR(Customer Specific Requirements)로 명시하고 있다.
아래 내용은 공개된 PPAP/APQP 가이드 및 협력사 교육 자료를 기반으로 정리한 것이다.

---

## PFMEA 관련 규칙·기준

### 현대·기아차 공통 요구사항

1. **기준 준수**: AIAG & VDA FMEA 1st Edition (2019) 적용 필수 (2021년부터 전환)
2. **AP 방식**: RPN 방식 불인정 → AP(H/M/L) 방식만 인정
3. **초기 FMEA 제출**: PPAP 제출 시 PFMEA 원본 포함 (Level 3 기준)
4. **개정 의무**: 아래 발생 시 30일 내 PFMEA 개정 제출
   - 공정 변경 (4M 변경: Man/Machine/Material/Method)
   - 동일 불량 3회 이상 재발
   - 고객 클레임 발생
   - 설계 변경
5. **보관 기간**: 양산 종료 후 최소 15년 보관
6. **특별특성 삼각 검증**: CC/SC 항목은 도면 ↔ PFMEA ↔ Control Plan 동일 표기 필수

### 특별특성 정의 (현대·기아 기준)

| 구분 | 기호 | 정의 | 요구사항 |
|---|---|---|---|
| CC (Critical Characteristic) | △ | 안전·법규에 직접 영향. 차량 안전에 위험 | 전수검사 또는 포카요케. SPC 의무 |
| SC (Significant Characteristic) | ◎ | 조립성, 주요 기능에 영향 | 통계적 관리 권고. CP에 관리 방법 명시 |

### PPAP 제출 요구사항 (PFMEA 관련)

| PPAP Level | PFMEA 제출 방식 |
|---|---|
| Level 1 | 제출 불필요 (보관만) |
| Level 2 | 요약본 또는 일부 샘플 제출 |
| Level 3 (일반) | PFMEA 원본 전체 제출 |
| Level 4 | 고객이 요청한 특정 양식으로 제출 |
| Level 5 | 현장 심사 시 원본 확인 |

---

## 한국GM 요구사항 (참고)

- AIAG 기준 준수 (AIAG-VDA 또는 기존 AIAG 4th Ed. 모두 인정)
- RPN 방식도 일부 인정 (프로그램별 상이)
- PFMEA는 제품 개발 초기부터 수행 요구 (선행 PFMEA)
- 공정 변경 시 PSW(Part Submission Warrant) 재발행 조건

---

## 주요 용어·정의

| 용어 | 정의 |
|---|---|
| PPAP | Production Part Approval Process — 양산 부품 승인 프로세스 |
| PSW | Part Submission Warrant — 부품 제출 보증서 (PPAP 핵심 문서) |
| APQP | Advanced Product Quality Planning — 사전 제품 품질 계획 |
| CSR | Customer Specific Requirements — 고객 특정 요구사항 |
| 4M 변경 | Man(작업자)/Machine(설비)/Material(소재)/Method(방법) 변경 |

---

## 체크리스트

- [ ] 고객사별 CSR 최신 버전을 확인했는가? (고객사 포털 또는 SQE 통해 입수)
- [ ] AP 방식을 사용하고 있는가? (현대·기아 납품 시 RPN 불인정)
- [ ] CC/SC 항목이 도면·PFMEA·CP 세 문서에 동일하게 표기되어 있는가?
- [ ] 고객 클레임 발생 시 30일 내 PFMEA 개정이 가능한 프로세스가 있는가?
- [ ] PPAP Level 3 기준 PFMEA 원본 제출 준비가 되어 있는가?
- [ ] 작성자·검토자·승인자 서명 및 날짜가 기입되어 있는가?

---
*공개된 PPAP/APQP 가이드 및 협력사 교육 자료 기반 | 자동 생성: 2026-04-25 | 최신 CSR은 반드시 고객사 SQE(Supplier Quality Engineer)로부터 직접 수령하여 확인*
