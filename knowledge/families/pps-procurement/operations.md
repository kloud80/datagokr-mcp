# 조달청 공공조달 API 패밀리 (나라장터·누리장터·쇼핑몰) — 오퍼레이션 전체 목록

> 자동 생성 (`python -m pds family-ops pps-procurement`). 원천: 조달청 OpenAPI 참고자료 docx. 손으로 고치지 말 것.
> 요청 파라미터의 `*`는 필수. 공통(serviceKey·pageNo·numOfRows·type)은 생략.
총 18개 서비스, 192개 오퍼레이션.

## 발주계획 — 나라장터 발주계획현황서비스 (15129462)

- 서비스 ID `OrderPlanSttusService` · 오퍼레이션 9개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getOrderPlanSttusListThng` | 발주계획현황에 대한 물품조회 | `inqryDiv`*, `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`, `orderPlanUntyNo`, `orderInsttCd`, `orderInsttNm` | 64 | 검색조건을 조회구분, 발주년월범위, 게시일자범위, 발주기관코드, 발주기관명, 발주계획통합번호로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 물품에 대한 발주계획현황 조회 |
| 2 | `getOrderPlanSttusListCnstwk` | 발주계획현황에 대한 공사조회 | `inqryDiv`*, `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`, `orderPlanUntyNo`, `orderInsttCd`, `orderInsttNm` | 64 | 검색조건을 조회구분, 발주년월범위, 게시일자범위, 발주기관코드, 발주기관명, 발주계획통합번호로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 공사에 대한 발주계획현황 조회 |
| 3 | `getOrderPlanSttusListServc` | 발주계획현황에 대한 용역조회 | `inqryDiv`*, `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`, `orderPlanUntyNo`, `orderInsttCd`, `orderInsttNm` | 64 | 검색조건을 조회구분, 발주년월범위, 게시일자범위, 발주기관코드, 발주기관명으로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 용역에 대한 발주계획현황 조회 |
| 4 | `getOrderPlanSttusListFrgcpt` | 발주계획현황에 대한 외자조회 | `inqryDiv`*, `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`, `orderPlanUntyNo`, `orderInsttCd`, `orderInsttNm` | 64 | 검색조건을 조회구분, 발주년월범위, 게시일자범위, 발주기관코드, 발주기관명으로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 외자에 대한 발주계획현황 조회 |
| 5 | `getOrderPlanSttusListThngPPSSrch` | 나라장터 검색조건에 의한 발주계획현황에 대한 물품조회 | `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`, `orderInsttCd`, `orderInsttNm`, `agrmntYn`, `prcrmntMethd`, `insttLctNm`, `dtilPrdctClsfcNo`, `bizNm` | 64 | 검색조건을 발주시작년월, 발주종료년월, 게시일시, 발주기관코드, 발주기관명, 협정여부, 조달방식, 기관소재지, 세부품명번호, 사업명으로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 물품에 대한 발주계획현황 조회 |
| 6 | `getOrderPlanSttusListCnstwkPPSSrch` | 나라장터 검색조건에 의한 발주계획현황에 대한 공사조회 | `orderBgnYm`, `orderEndYm`*, `inqryBgnDt`, `inqryEndDt`, `orderInsttCd`, `orderInsttNm`, `bsnsTyCd`, `bsnsTyNm`, `prcrmntMethd`, `insttLctNm`, `cnsttyDivNm`, `bizNm` | 64 | 검색조건을 발주시작년월, 발주종료년월, 게시일시, 발주기관코드, 발주기관명, 업무유형, 조달방식, 기관소재지, 공종, 사업명으로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 공사에 대한 발주계획현황 조회 |
| 7 | `getOrderPlanSttusListServcPPSSrch` | 나라장터 검색조건에 의한 발주계획현황에 대한 용역조회 | `orderBgnYm`, `orderEndYm`, `inqryBgnDt`, `inqryEndDt`, `orderInsttCd`, `orderInsttNm`, `bsnsTyCd`, `bsnsTyNm`, `prcrmntMethd`, `insttLctNm`, `cnsttyDivNm`, `bizNm` | 64 | 검색조건을 발주시작년월, 발주종료년월, 게시일시, 발주기관코드, 발주기관명, 업무유형, 조달방식, 기관소재지, 공종, 사업명으로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 용역에 대한 발주계획현황 조회 |
| 8 | `getOrderPlanSttusListFrgcptPPSSrch` | 나라장터 검색조건에 의한 발주계획현황에 대한 외자조회 | `orderBgnYm`, `orderEndYm`, `inqryBgnDt`*, `inqryEndDt`, `orderInsttCd`, `orderInsttNm`, `bsnsTyCd`, `bsnsTyNm`, `prcrmntMethd`, `insttLctNm`, `bizNm` | 64 | 검색조건을 발주시작년월, 발주종료년월, 게시일시, 발주기관코드, 발주기관명, 업무유형, 조달방식, 기관소재지, 사업명으로 하여 발주년도, 발주기관, 소관기관, 계약방법, 발주도급금액, 물품분류 정보, 규격항목정보 등 외자에 대한 발주계획현황 조회 |
| 9 | `getOrderPlanSttusAtchFileList` | 발주계획현황에 대한 첨부파일 목록조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `orderPlanUntyNo`, `bsnsDivCd`* | 15 | 게시일시, 발주계획통합번호의 검색조건을 통해 발주계획의 첨부파일 정보를조회(업무구분코드, 업무구분명, 발주계획통합번호, 발주계획순번, 발주년월, 게시일시, 사업명, 첨부파일수번, 첨부파일명, 첨부파일URL) |

## 조달요청 — 나라장터 조달요청서비스 (15129468)

- 서비스 ID `PrcrmntReqInfoService` · 오퍼레이션 12개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPrcrmntReqInfoListThng` | 조달요청에 대한 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `prcrmntReqNo` | 29 | 검색조건을 조회구분, 입력일시, 접수번호 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 물품에 대한 조달요청 조회 |
| 2 | `getPrcrmntReqInfoListThngDetail` | 조달요청에 대한 물품세부조회 | `prcrmntReqNo`* | 20 | 검색조건을 조달요청번호를 입력하여 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 물품세부에 대한 조달요청 조회 |
| 3 | `getPrcrmntReqInfoListThngPPSSrch` | 나라장터검색조건에 의한 조달요청 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `prcrmntReqNo`, `rcptBrnofceNm`, `prdctClsfcNoNm`, `orderInsttCd`, `orderInsttNm`, `prdctClsfcNo`, `reqDivCd`, `specDocYn` | 29 | 나라장터 검색조건(조회구분, 접수일시, 결재일시, 조달요청번호, 접수기관 품명) 등을 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 물품에 대한 조달요청 조회 |
| 4 | `getPrcrmntReqInfoListCnstwk` | 조달요청에 대한 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `prcrmntReqNo` | 35 | 검색조건을 조회구분, 입력일시, 조달요청번호를 입력하여 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 공사에 대한 조달요청 조회 |
| 5 | `getPrcrmntReqInfoListCnstwkPPSSrch` | 나라장터검색조건에 의한 조달요청 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `rcptBrnofceNm`, `prcrmntReqNm`, `orderInsttCd`, `orderInsttNm`, `prcrmntReqNo` | 35 | 나라장터 검색조건(조회구분, 접수일시, 조달요청번호, 접수지청명, 조달요청명, 발주기관, 조달요청번호) 등을 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 공사에 대한 조달요청 조회 |
| 6 | `getPrcrmntReqInfoListGnrlServc` | 조달요청에 대한 일반용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `prcrmntReqNo` | 29 | 검색조건을 조회구분, 입력일시, 접수번호 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 일반용역에 대한 조달요청 조회 |
| 7 | `getPrcrmntReqInfoListGnrlServcPPSSrch` | 나라장터검색조건에 의한 조달요청 일반용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `rcptBrnofceNm`, `prdctClsfcNoNm`, `orderInsttCd`, `orderInsttNm`, `prdctClsfcNo`, `reqDivCd`, `specDocYn`, `prcrmntReqNo` | 29 | 나라장터 검색조건(조회구분, 접수일시, 조달요청번호, 접수지청명, 조달요청명, 발주기관, 조달요청번호) 등을 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 일반용역에 대한 조달요청 조회 |
| 8 | `getPrcrmntReqInfoListTechServc` | 조달요청에 대한 기술용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `prcrmntReqNo` | 31 | 검색조건을 조회구분, 입력일시, 접수번호 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 기술용역에 대한 조달요청 조회 |
| 9 | `getPrcrmntReqInfoListTechServcPPSSrch` | 나라장터검색조건에 의한 조달요청 기술용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `rcptBrnofceNm`, `orderInsttCd`, `orderInsttNm`, `prcrmntReqNo` | 31 | 나라장터 검색조건(조회구분, 접수일시, 조달요청번호, 접수지청명, 조달요청명, 발주기관, 조달요청번호) 등을 입력하여 조달요청번호, 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 기술용역에 대한 조달요청 조회 |
| 10 | `getPrcrmntReqInfoListFrgcpt` | 조달요청에 대한 외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `prcrmntReqNo` | 16 | 검색조건을 조회구분, 입력일시, 조달요청번호를 입력하여 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 외자에 대한 조달요청 조회 |
| 11 | `getPrcrmntReqInfoListFrgcptDetail` | 조달요청에 대한 외자세부조회 | `prcrmntReqNo`* | 26 | 검색조건을 조달요청번호를 입력하여 계약체결형태명, 대표납품장소, 발주기관, 조달요청명 등 외자세부에 대한 조달요청 조회 |
| 12 | `getPrcrmntReqInfoListFrgcptPPSSrch` | 나라장터검색조건에 의한 조달요청 외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `engRprsntPrdctNm`, `dminsttCd`, `dminsttNm`, `cptalDivCd`, `ofclDeptDivCd`, `prcrmntReqNo` | 16 | 나라장터 검색조건(조회구분, 접수일시, 조달요청번호, 영문대표물품명, 발주기관, 조달요청번호) 등을 입력하여 조달요청번호, 발주기관, 영문대표물품명, 전체품목건수, 배정미화금액 등 외자에 대한 조달요청 조회 |

## 사전규격 — 나라장터 사전규격정보서비스 (15129437)

- 서비스 ID `HrcspSsstndrdInfoService` · 오퍼레이션 20개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPublicPrcureThngInfoThng` | 사전규격 물품 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 28 | 검색조건을 조회구분, 등록일시범위, 변경일시범위, 사전규격등록번호로 입력하여 물품에 대한 사전규격등록번호, 품명, 발주기관명, 수요기관명, 관련 규격문서파일 등 나라장터 사전규격정보목록을 조회 |
| 2 | `getInsttAcctoThngListInfoThng` | 사전규격 물품 기관별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `orderInsttNm`, `rlDminsttNm` | 27 | 물품에 대한 사전규격정보를 기관별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 발주기관명, 실수요기관명 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 물품에 대한 나라장터 사전규격정보 기관별 목록을 조회 |
| 3 | `getThngDetailMetaInfoThng` | 사전규격 물품 품목별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `prdctClsfcNoNm`, `dtilPrdctClsfcNo`, `dtilPrdctClsfcNoNm` | 28 | 물품에 대한 사전규격정보를 품목별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 품명으로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 물품에 대한 나라장터 사전규격정보 품목별 목록을 조회 |
| 4 | `getPublicPrcureThngInfoFrgcpt` | 사전규격 외자 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 27 | 검색조건을 조회구분, 등록일시범위, 변경일시범위, 사전규격등록번호로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 외자에 대한 나라장터 사전규격정보목록을 조회 |
| 5 | `getInsttAcctoThngListInfoFrgcpt` | 사전규격 외자 기관별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `orderInsttNm`, `rlDminsttNm` | 27 | 외자에 대한 사전규격정보를 기관별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 발주기관명, 수요기관명으로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 외자에 대한 나라장터 사전규격정보 기관별 목록을 조회 |
| 6 | `getThngDetailMetaInfoFrgcpt` | 사전규격 외자 품목별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `prdctClsfcNoNm` | 27 | 외자에 대한 사전규격정보를 품목별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 품명으로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 외자에 대한 나라장터 사전규격정보 품목별 목록을 조회 |
| 7 | `getPublicPrcureThngInfoServc` | 사전규격 용역 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 28 | 검색조건을 조회구분, 등록일시범위, 변경일시범위, 사전규격등록번호로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 용역에 대한 나라장터 사전규격정보목록을 조회 |
| 8 | `getInsttAcctoThngListInfoServc` | 사전규격 용역 기관별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `orderInsttNm`, `rlDminsttNm` | 28 | 용역에 대한 사전규격정보를 기관별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 발주기관명, 수요기관명으로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 용역에 대한 나라장터 사전규격정보 기관별 목록을 조회 |
| 9 | `getThngDetailMetaInfoServc` | 사전규격 용역 품목별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `prdctClsfcNoNm`, `dtilPrdctClsfcNo`, `dtilPrdctClsfcNoNm` | 28 | 용역에 대한 사전규격정보를 품목별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 품명, 세부품명, 세부품명번호로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 용역에 대한 나라장터 사전규격정보 품목별 목록을 조회 |
| 10 | `getPublicPrcureThngInfoCnstwk` | 사전규격 공사 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 27 | 검색조건을 조회구분, 등록일시범위, 변경일시범위, 사전규격등록번호로 입력하여 공사에 대한 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 나라장터 사전규격정보목록을 조회 |
| 11 | `getInsttAcctoThngListInfoCnstwk` | 사전규격 공사 기관별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `orderInsttNm`, `rlDminsttNm` | 27 | 공사에 대한 사전규격정보를 기관별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 발주기관명, 수요기관명으로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 공사에 대한 나라장터 사전규격정보 기관별 목록을 조회 |
| 12 | `getThngDetailMetaInfoCnstwk` | 사전규격 공사 품목별 목록 조회 | `inqryBgnDt`, `inqryEndDt`, `prdctClsfcNoNm` | 27 | 공사에 대한 사전규격정보를 품목별로 조회할 수 있는 오퍼레이션으로 검색조건을 등록일시범위, 품명으로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 공사에 대한 나라장터 사전규격정보 품목별 목록을 조회 |
| 13 | `getPublicPrcureThngInfoThngPPSSrch` | 나라장터 검색조건에 의한 사전규격 물품 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo`, `refNo`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `prdctClsfcNoNm`, `swBizObjYn`, `dtilPrdctClsfcNo` | 28 | 검색조건을 조회구분, 접수일시범위, 사전규격등록번호, 참조번호, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 품명, SW사업대상여부, 세부품명번호로 입력하여 물품에 대한 사전규격등록번호, 품명, 발주기관명, 수요기관명, 관련 규격문서파일 등 나라장터 사전규격정보목록을 조회 |
| 14 | `getPublicPrcureThngInfoFrgcptPPSSrch` | 나라장터 검색조건에 의한 사전규격 외자 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo`, `refNo`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `prdctClsfcNoNm`, `swBizObjYn` | 27 | 검색조건을 조회구분, 접수일시범위, 사전규격등록번호, 참조번호, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 품명, SW사업대상여부로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 외자에 대한 나라장터 사전규격정보목록을 조회 |
| 15 | `getPublicPrcureThngInfoServcPPSSrch` | 나라장터 검색조건에 의한 사전규격 용역 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo`, `refNo`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `prdctClsfcNoNm`, `swBizObjYn`, `dtilPrdctClsfcNo` | 28 | 검색조건을 조회구분, 접수일시범위, 사전규격등록번호, 참조번호, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 품명, SW사업대상여부, 세부품명번호 로 입력하여 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 용역에 대한 나라장터 사전규격정보목록을 조회 |
| 16 | `getPublicPrcureThngInfoCnstwkPPSSrch` | 나라장터 검색조건에 의한 사전규격 공사 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo`, `refNo`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `prdctClsfcNoNm` | 27 | 검색조건을 조회구분, 접수일시범위, 사전규격등록번호, 참조번호, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 품명으로 입력하여 공사에 대한 사전규격등록번호, 품명, 발주기관, 수요기관, 관련 규격문서파일 등 나라장터 사전규격정보목록을 조회 |
| 17 | `getPublicPrcureThngOpinionInfoThng` | 나라장터 사전규격 물품 규격서 의견 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 21 | 검색조건을 조회구분, 등록일시범위, 사전규격등록번호로 입력하여 사전규격등록번호, 참조번호, 의견제목, 작성업체명, 작성자명, 입력일시, 작성자전화번호, 작성자이메일, 관련 규격서의견파일, 의견내용 등 나라장터 사전규격 물품 규격서 의견 목록을 조회 |
| 18 | `getPublicPrcureThngOpinionInfoFrgcpt` | 나라장터 사전규격 외자 규격서 의견 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 21 | 검색조건을 조회구분, 등록일시범위, 사전규격등록번호로 입력하여 사전규격등록번호, 참조번호, 의견제목, 작성업체명, 작성자명, 입력일시, 작성자전화번호, 작성자이메일, 관련 규격서의견파일, 의견내용 등 나라장터 사전규격 외자 규격서 의견 목록을 조회 |
| 19 | `getPublicPrcureThngOpinionInfoServc` | 나라장터 사전규격 용역 규격서 의견 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 21 | 검색조건을 조회구분, 등록일시범위, 사전규격등록번호로 입력하여 사전규격등록번호, 참조번호, 의견제목, 작성업체명, 작성자명, 입력일시, 작성자전화번호, 작성자이메일, 관련 규격서의견파일, 의견내용 등 나라장터 사전규격 용역 규격서 의견 목록을 조회 |
| 20 | `getPublicPrcureThngOpinionInfoCnstwk` | 나라장터 사전규격 공사 규격서 의견 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bfSpecRgstNo` | 21 | 검색조건을 조회구분, 등록일시범위, 사전규격등록번호로 입력하여 사전규격등록번호, 참조번호, 의견제목, 작성업체명, 작성자명, 입력일시, 작성자전화번호, 작성자이메일, 관련 규격서의견파일, 의견내용 등 나라장터 사전규격 공사 규격서 의견 목록을 조회 |

## 입찰공고 — 나라장터 입찰공고정보서비스 (15129394)

- 서비스 ID `BidPublicInfoService` · 오퍼레이션 25개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getBidPblancListInfoCnstwk` | 입찰공고목록 정보에 대한 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 148 | 검색조건에 등록일시, 입찰공고번호, 변경일시를 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 공사부분의 입찰공고정보를 조회함 |
| 2 | `getBidPblancListInfoServc` | 입찰공고목록 정보에 대한 용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 118 | 검색조건에 등록일시, 입찰공고번호, 변경일시를 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 용역부분의 입찰공고정보를 조회함 |
| 3 | `getBidPblancListInfoFrgcpt` | 입찰공고목록 정보에 대한 외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 102 | 검색조건에 등록일시, 입찰공고번호, 변경일시를 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 외자 부분의 입찰공고정보를 조회함 |
| 4 | `getBidPblancListInfoThng` | 입찰공고목록 정보에 대한 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 106 | 검색조건에 등록일시, 입찰공고번호, 변경일시를 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 물품부분의 입찰공고정보를 조회함 |
| 5 | `getBidPblancListInfoThngBsisAmount` | 입찰공고목록 정보에 대한 물품기초금액조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 29 | 검색조건에 기초금액 등록일시, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고명, 기초금액, 기초금액공개일시, 예비가격범위시작율, 평가기준금액, 난이도계수, 기타경비기준율 등 물품의 기초금액정보 조회 |
| 6 | `getBidPblancListInfoCnstwkBsisAmount` | 입찰공고목록 정보에 대한 공사기초금액조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 37 | 검색조건에 기초금액 등록일시, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고명, 기초금액, 기초금액공개일시, 예비가격범위시작율, 평가기준금액, 난이도계수, 기타경비기준율 등의 공사의 기초금액정보 조회 |
| 7 | `getBidPblancListInfoServcBsisAmount` | 입찰공고목록 정보에 대한 용역기초금액조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 31 | 검색조건에 기초금액 등록일시, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고명, 기초금액, 기초금액공개일시, 예비가격범위시작율, 평가기준금액, 난이도계수, 기타경비기준율 등의 용역의 기초금액정보 조회 |
| 8 | `getBidPblancListInfoChgHstryThng` | 입찰공고목록 정보에 대한 물품변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 16 | 검색조건에 변경일시, 입찰공고번호를 입력하여 변경된 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 변경항목명, 변경전후값 등 물품 입찰공고변경 데이터 조회 ※ 변경이력 추출 대상 항목 PQ신청서접수일시, 물품분류제한여부, 제조여부, 입찰서개시일시, 입찰서마감일시, 개찰일시, 입찰자격등록일시, 공동수급협정서마감일시, PQ신청서접수방법명, 참가가능지역, 면허제한코드, 설명회실시일시, 입 |
| 9 | `getBidPblancListInfoChgHstryCnstwk` | 입찰공고목록 정보에 대한 공사변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 16 | 검색조건에 변경일시, 입찰공고번호를 입력하여 변경된 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 변경항목명, 변경전후값 등 공사 입찰공고변경 데이터 조회 ※ 변경이력 추출 대상 항목 PQ신청서접수일시, 물품분류제한여부, 제조여부, 입찰서개시일시, 입찰서마감일시, 개찰일시, 입찰자격등록일시, 공동수급협정서마감일시, PQ신청서접수방법명, 참가가능지역, 면허제한코드, 설명회실시일시, 입 |
| 10 | `getBidPblancListInfoChgHstryServc` | 입찰공고목록 정보에 대한 용역변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 16 | 검색조건에 변경일시, 입찰공고번호를 입력하여 변경된 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 변경항목명, 변경전후값 등 용역 입찰공고변경 데이터 조회 ※ 변경이력 추출 대상 항목 PQ신청서접수일시, 물품분류제한여부, 제조여부, 입찰서개시일시, 입찰서마감일시, 개찰일시, 입찰자격등록일시, 공동수급협정서마감일시, PQ신청서접수방법명, 참가가능지역, 면허제한코드, 설명회실시일시, 입 |
| 11 | `getBidPblancListInfoCnstwkPPSSrch` | 나라장터검색조건에 의한 입찰공고공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 148 | 검색조건에 공고게시일시, 개찰일시 범위, 공고기관, 수요기관, 참조번호 등을 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 공사부분의 입찰공고정보를 조회함 |
| 12 | `getBidPblancListInfoServcPPSSrch` | 나라장터검색조건에 의한 입찰공고용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 117 | 검색조건에 공고게시일시, 개찰일시 범위, 공고기관, 수요기관, 참조번호 등을 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 용역부분의 입찰공고정보를 조회함 |
| 13 | `getBidPblancListInfoFrgcptPPSSrch` | 나라장터검색조건에 의한 입찰공고외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 102 | 검색조건에 공고게시일시, 개찰일시 범위, 공고기관, 수요기관, 참조번호 등을 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 외자부분의 입찰공고정보를 조회함 |
| 14 | `getBidPblancListInfoThngPPSSrch` | 나라장터검색조건에 의한 입찰공고물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 106 | 검색조건에 공고게시일시, 개찰일시 범위, 공고기관, 수요기관, 참조번호 등을 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 물품부분의 입찰공고정보를 조회함 |
| 15 | `getBidPblancListInfoLicenseLimit` | 입찰공고목록 정보에 대한 면허제한정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 14 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 제한그룹번호, 제한순번, 면허제한명, 허용업종목록, 등록일시를 포함한 면허제한정보 조회 |
| 16 | `getBidPblancListInfoPrtcptPsblRgn` | 입찰공고목록 정보에 대한 참가가능지역정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 11 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 제한그룹번호, 참가가능지역명, 등록일시 등 참가가능지역정보조회 |
| 17 | `getBidPblancListInfoThngPurchsObjPrdct` | 입찰공고목록 정보에 대한 물품 구매대상물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 24 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰분류번호, 물품순번, 수요기관코드, 수요기관명, 물품분류번호, 품명, 세부품명번호, 세부품명, 수량, 단위, 단가, 납품기한일시, 납품일수, 납품장소, 인도조건명 등 물품 구매대상물품 정보 조회 |
| 18 | `getBidPblancListInfoServcPurchsObjPrdct` | 입찰공고목록 정보에 대한 용역 구매대상물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 24 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰분류번호, 물품순번, 수요기관코드, 수요기관명, 물품분류번호, 품명, 세부품명번호, 세부품명, 수량, 단위, 단가, 납품기한일시, 납품일수, 납품장소, 인도조건명 등 용역 구매대상물품 정보 조회 |
| 19 | `getBidPblancListInfoFrgcptPurchsObjPrdct` | 입찰공고목록 정보에 대한 외자 구매대상물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 19 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰분류번호, 물품순번, 수요기관코드, 수요기관명, HSK번호, 세부품명번호, 세부품명, 수량, 단위, 배정금액, 배정금액통화 등 외자 구매대상물품 정보 조회 |
| 20 | `getBidPblancListInfoEorderAtchFileInfo` | 입찰공고목록 정보에 대한 e발주 첨부파일정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 11 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 첨부순번, e발주문서구분명, e발주첨부파일명, e발주첨부파일URL 정보 조회 |
| 21 | `getBidPblancListInfoEtc` | 입찰공고목록 정보에 대한 기타공고조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 43 | 검색조건에 등록일시, 입찰공고번호를 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 기타공고정보를 조회 |
| 22 | `getBidPblancListInfoEtcPPSSrch` | 나라장터검색조건에 의한 입찰공고 기타조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttNm`, `refNo`, `presmptPrceBgn`, `presmptPrceEnd`, `bidClseExcpYn` | 43 | 검색조건에 공고게시일시, 개찰일시 범위, 공고기관, 수요기관, 참조번호 등을 입력하여 나라장터의 입찰공고번호, 공고명, 발주기관, 수요기관, 계약체결방법명 등 공사부분의 입찰공고정보를 조회함 |
| 23 | `getBidPblancListPPIFnlRfpIssAtchFileInfo` | 입찰공고목록 정보에 대한 혁신장터 최종제안요청서 교부 첨부파일정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 13 | 낙찰자결정방법이 [경쟁적 대화에 의한 낙찰자 선정 낙찰방법] 일경우 검색조건에 등록일시, 입찰공고번호, 교부일시를 입력하여 혁신장터에서 교부된 최종제안요청서 첨부파일정보를 조회함 |
| 24 | `getBidPblancListBidPrceCalclAInfo` | 입찰공고목록 정보에 대한 입찰가격산식A정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 20 | 검색조건에 공고게시일시와 입찰공고번호를 입력하여 입찰가격산식 A값 적용 공고의 합산항목인 국민연금보험료, 국민건강보험료, 퇴직공제부금비, 노인장기요양보험료, 산업안전보건관리비, 안전관리비, 품질관리비, 품질관리비 적용대상여부등  입찰가격산식A정보 조회 ( 복수예가는 A값 공개 시 제공) |
| 25 | `getBidPblancListEvaluationIndstrytyMfrcInfo` | 입찰공고목록 정보에 대한 평가대상주력분야 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 19 | 검색조건에 등록일시와 입찰공고번호를 입력하여 입찰 평가대상주력분야의 건산법적용여부, 건설업역상호진출가능여부, 건설업역구분코드, 낙찰자선정적용기준코드, 공종유형명, 공사대상업종명, 업종주력분야명, 추정금액, 추정가격, 부가가치세, 평가비율을 조회 |

## 낙찰 — 나라장터 낙찰정보서비스 (15129397)

- 서비스 ID `ScsbidInfoService` · 오퍼레이션 23개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getScsbidListSttusThng` | 낙찰된 목록 현황 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 25 | 검색조건을 등록일시, 공고일시, 개찰일시, 입찰공고번호로 물품에 대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일시, 수요기관, 최종낙찰일, 최종낙찰업체담당자)을 조회 |
| 2 | `getScsbidListSttusCnstwk` | 낙찰된 목록 현황 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 25 | 검색조건을 등록일시, 공고일시, 개찰일시, 입찰공고번호로 공사에대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일시, 수요기관, 최종낙찰일, 최종낙찰업체담당자)을 조회 |
| 3 | `getScsbidListSttusServc` | 낙찰된 목록 현황 용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 25 | 검색조건을 등록일시, 공고일시, 개찰일시, 입찰공고번호로 용역에 대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일시, 수요기관, 최종낙찰일, 최종낙찰업체담당자)을 조회 |
| 4 | `getScsbidListSttusFrgcpt` | 낙찰된 목록 현황 외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 25 | 검색조건을 등록일시, 공고일시, 개찰일시, 입찰공고번호로 외자에 대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일시, 수요기관, 최종낙찰일, 최종낙찰업체담당자)을 조회 |
| 5 | `getOpengResultListInfoThng` | 개찰결과 물품 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 입력일시, 공고일시, 개찰일시, 입찰공고번호로하여 물품에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰일시, 참가업체수, 개찰업체정보, 진행구분코드명, 입력일시, 예비가격파일존재여부, 공고기관명, 수요기관명)을 조회 |
| 6 | `getOpengResultListInfoCnstwk` | 개찰결과 공사 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 입력일시, 공고일시, 개찰일시, 입찰공고번호로하여 공사에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰일시, 참가업체수, 개찰업체정보, 진행구분코드명, 입력일시, 예비가격파일존재여부, 공고기관명, 수요기관명)을 조회 |
| 7 | `getOpengResultListInfoServc` | 개찰결과 용역 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 입력일시, 공고일시, 개찰일시, 입찰공고번호로하여 용역에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰일시, 참가업체수, 개찰업체정보, 진행구분코드명, 입력일시, 예비가격파일존재여부, 공고기관명, 수요기관명)을 조회 |
| 8 | `getOpengResultListInfoFrgcpt` | 개찰결과 외자 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 입력일시, 공고일시, 개찰일시, 입찰공고번호로하여 외자에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰일시, 참가업체수, 개찰업체정보, 진행구분코드명, 입력일시, 예비가격파일존재여부, 공고기관명, 수요기관명)을 조회 |
| 9 | `getOpengResultListInfoThngPreparPcDetail` | 개찰결과 물품 예비가격상세 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 23 | 검색조건을 입력일시, 입찰공고번호로 물품에 대한 나라장터 개찰결과 예비가격상세 목록(입찰공고번호, 입찰공고명, 예정가격, 기초금액, 총예가건수, 복수예가순번, 기초예정가격, 추첨여부, 추첨횟수, 실개찰일시, 기초금액기준상위건수, 복수예비가격작성일시, 입력일시)을 조회 |
| 10 | `getOpengResultListInfoCnstwkPreparPcDetail` | 개찰결과 공사 예비가격상세 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 23 | 검색조건을 등록일시, 입찰공고번호로 공사에 대한 나라장터 개찰결과 예비가격상세 목록(입찰공고번호, 입찰공고명, 예정가격, 기초금액, 총예가건수, 복수예가순번, 기초예정가격, 추첨여부, 추첨횟수, 실개찰일시, 기초금액기준상위건수, 복수예비가격작성일시, 입력일시)을 조회 |
| 11 | `getOpengResultListInfoServcPreparPcDetail` | 개찰결과 용역 예비가격상세 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 23 | 검색조건을 등록일시, 입찰공고번호로 용역에 대한 나라장터 개찰결과 예비가격상세 목록(입찰공고번호, 입찰공고명, 예정가격, 기초금액, 총예가건수, 복수예가순번, 기초예정가격, 추첨여부, 추첨횟수, 실개찰일시, 기초금액기준상위건수, 복수예비가격작성일시, 입력일시)을 조회 |
| 12 | `getOpengResultListInfoFrgcptPreparPcDetail` | 개찰결과 외자 예비가격상세 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 23 | 검색조건을 등록일시, 입찰공고번호로 외자에 대한 나라장터 개찰결과 외자 예비가격상세 목록(입찰공고번호, 입찰공고명, 예정가격, 기초금액, 총예가건수, 복수예가순번, 기초예정가격, 추첨여부, 추첨횟수, 실개찰일시, 기초금액기준상위건수, 복수예비가격작성일시, 입력일시)을 조회 |
| 13 | `getOpengResultListInfoOpengCompt` | 개찰결과 개찰완료 목록 조회 | `bidNtceNo`*, `bidNtceOrd`, `bidClsfcNo`, `rbidNo` | 25 | 물품, 공사, 용역, 외자의 개찰완료된 건에 대하여 최종낙찰업체 및 투찰업체의 개찰순위 정보를 제공하며 검색조건을 입찰공고번호하여 나라장터 개찰결과 개찰완료 목록(개찰결과구분명, 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 개찰순위, 최종낙찰업체사업자등록번호, 최종낙찰업체명, 최종낙찰업체대표자명, 투찰금액, 투찰룰, 비고, 공종별입찰금액URL), 추첨번호1, 추첨번호2, 투찰일시  |
| 14 | `getOpengResultListInfoFailing` | 개찰결과 유찰 목록 조회 | `bidNtceNo`*, `bidNtceOrd`, `bidClsfcNo`, `rbidNo` | 11 | 검색조건을 입찰공고번호 입력하여 물품, 공사, 용역, 외자의 나라장터 개찰결과 유찰 목록(개찰결과구분명, 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 유찰사유)을 조회 |
| 15 | `getOpengResultListInfoRebid` | 개찰결과 재입찰 목록 조회 | `bidNtceNo`*, `bidNtceOrd`, `bidClsfcNo`, `rbidNo` | 14 | 검색조건을 입찰공고번호 입력하여 물품, 공사, 용역, 외자의 나라장터 개찰결과 재입찰 목록(개찰결과구분명, 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 입찰마감일시, 개찰일시, 재입찰사유, 공동수급협정마감일시)을 조회. |
| 16 | `getScsbidListSttusThngPPSSrch` | 나라장터 검색조건에 의한 낙찰된 목록 현황 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd`, `bizno` | 25 | 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 물품에 대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일 |
| 17 | `getScsbidListSttusCnstwkPPSSrch` | 나라장터 검색조건에 의한 낙찰된 목록 현황 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd`, `bizno` | 25 | 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 공사에대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일시 |
| 18 | `getScsbidListSttusServcPPSSrch` | 나라장터 검색조건에 의한 낙찰된 목록 현황 용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd`, `bizno` | 25 | 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 용역에 대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일 |
| 19 | `getScsbidListSttusFrgcptPPSSrch` | 나라장터 검색조건에 의한 낙찰된 목록 현황 외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd`, `bizno` | 25 | 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 외자에 대한 나라장터 최종낙찰자 목록(입찰공고번호, 입찰공고명, 참가업체수, 최종낙찰업체명, 사업자번호, 최종낙찰률, 실개찰일 |
| 20 | `getOpengResultListInfoThngPPSSrch` | 나라장터 검색조건에 의한 개찰결과 물품 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 하여 물품에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰 |
| 21 | `getOpengResultListInfoCnstwkPPSSrch` | 나라장터 검색조건에 의한 개찰결과 공사 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 하여 공사에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰 |
| 22 | `getOpengResultListInfoServcPPSSrch` | 나라장터 검색조건에 의한 개찰결과 용역 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로하여 용역에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰일 |
| 23 | `getOpengResultListInfoFrgcptPPSSrch` | 나라장터 검색조건에 의한 개찰결과 외자 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd` | 21 | 유찰, 개찰완료, 재입찰건에 대한 개찰결과를 제공하며 검색조건을 공고일시, 개찰일시, 입찰공고번호, 입찰공고명, 공고기관코드, 공고기관명, 수요기관코드, 수요기관명, 참조번호, 참가제한지역코드, 참가제한지역명, 업종코드, 업종명, 추정가격시작, 추정가격종료, 세부품명번호, 다수공급경쟁자여부, 조달요청번호, 국제구분코드로 하여 외자에 대한 나라장터 개찰결과 목록(입찰공고번호, 입찰공고명, 개찰 |

## 계약 — 나라장터 계약정보서비스 (15129427)

- 서비스 ID `CntrctInfoService` · 오퍼레이션 21개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getCntrctInfoListThng` | 계약현황에 대한 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 44 | 검색조건을 등록일시, 통합계약번호 등을 입력하여 물품 계약현황 (통합계약번호, 계약구분, 확정계약번호, 계약참조번호, 계약건명, 공동계약여부, 장기계속구분, 계약체결일자, 계약기간, 근거법률, 총계약금액, 금차계약금액, 보증금률, 링크URL, 지급구분, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계약기관소관구분, 계약기관담당부서명, 계약기관담당자명, 계약기관담당자전화번호, 계약기관담당자 |
| 2 | `getCntrctInfoListThngDetail` | 계약현황에 대한 물품세부조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 24 | 검색조건을 등록일시, 통합계약번호 등을 입력하여 물품 계약세부현황 (계약체결일자, 통합계약번호, 확정계약번호, 계약참조번호, 물품분류번호, 물품식별번호, 품명, 한글품목명, 원산지코드, 원산지명, 수량단가금액, 물품수량, 물품금액, 인도조건코드, 인도조건명, 납품일수, 납품기한) 정보를 조회 |
| 3 | `getCntrctInfoListThngPPSSrch` | 나라장터검색조건에 의한 계약현황 물품조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `insttDivCd`, `insttClsfcCd`, `insttCd`, `insttNm`, `prdctClsfcNoNm`, `cntrctMthdCd`, `cntrctRefNo`, `cntrctDivCd`, `dcsnCntrctNo`, `reqNo`, `ntceNo` | 44 | 나라장터 검색조건인 계약체결일자, 확정계약번호, 요청번호, 공고번호, 기관분류, 계약기관, 기관명, 품명, 계약방법, 계약참조번호를 입력하면 물품계약정보(통합계약번호, 계약구분, 확정계약번호, 계약참조번호, 계약건명, 공동계약여부, 장기계속구분, 계약체결일자, 계약기간, 근거법률, 총계약금액, 금차계약금액, 보증금률, 링크URL, 지급구분, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계 |
| 4 | `getCntrctInfoListThngChgHstry` | 계약현황에 대한 물품변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 39 | 계약현황에 대한 물품변경이력조회 |
| 5 | `getCntrctInfoListThngDltHstry` | 계약현황에 대한 물품삭제이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 12 | 검색조건에 삭제일시, 통합계약번호를 입력하여 물품 계약삭제이력정보( 삭제일시, 변경구분명, 통합계약번호, 확정계약번호, 계약참조번호) 조회 |
| 6 | `getCntrctInfoListCnstwk` | 계약현황에 대한 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 48 | 검색조건을 등록일시, 통합계약번호 등을 입력하여 공사 계약현황 (통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계약기관소관구분명, 계약기관담당부서명, 계약기관담당자명, 계약기관담당자전화번호, 계 |
| 7 | `getCntrctInfoListCnstwkServcInfo` | 계약현황에 대한 공사서비스정보조회 | `untyCntrctNo`* | 12 | 검색조건에 통합계약번호를 입력하여 공사서비스정보(통합계약번호, 대표여부,업종명, 공사현장지역명, 공사금액) 조회 |
| 8 | `getCntrctInfoListCnstwkPPSSrch` | 나라장터검색조건에 의한 계약현황 공사조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `insttDivCd`, `insttClsfcCd`, `insttCd`, `insttNm`, `cnsttyNm`, `cnstwkNm`, `cntrctMthdCd`, `cntrctRefNo`, `cntrctDivCd`, `dcsnCntrctNo`, `reqNo`, `ntceNo` | 48 | 나라장터 검색조건인 계약체결일자, 확정계약번호, 요청번호, 공고번호, 기관분류(계약기관), 기관명, 공종명, 공사명, 계약방법코드, 계약참조번호 등을 입력하면 공사계약정보(통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계 |
| 9 | `getCntrctInfoListCnstwkChgHstry` | 계약현황에 대한 공사변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 43 | 검색조건에 변경일시,통합계약번호를 입력하여 공사 계약변경정보(통합계약번호,업무명,확정계약번호,계약참조번호,계약명,공동계약여부,장기계속구분명,계약체결일자,계약기간,근거법률,총계약금액,금차계약금액,보증금률,계약사이트URL,지급구분명,요청번호,공고번호,계약기관코드,계약기관명,계약기관소관구분,계약기관담당부서명,계약기관담당자명,계약기관담당자전화번호 ,계약기관담당자팩스번호,수요기관코드,수요기관명,수요기 |
| 10 | `getCntrctInfoListCnstwkDltHstry` | 계약현황에 대한 공사삭제이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 12 | 검색조건에 삭제일시, 통합계약번호를 입력하여 공사 계약삭제이력정보( 삭제일시, 변경구분명, 통합계약번호, 확정계약번호, 계약참조번호) 조회 |
| 11 | `getCntrctInfoListServc` | 계약현황에 대한 용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 47 | 검색조건을 등록일시, 통합계약번호 등을 입력하여 용역 계약현황 (통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계약기관소관구분명, 계약기관담당부서명, 계약기관담당자명, 계약기관담당자전화번호, 계 |
| 12 | `getCntrctInfoListGnrlServcServcInfo` | 계약현황에 대한 일반용역서비스정보조회 | `untyCntrctNo`* | 12 | 검색조건에 통합계약번호를 입력하여 일반용역서비스정보(통합계약번호, 대표여부, 품명및규격, 지역명, 공사금액) 조회 |
| 13 | `getCntrctInfoListTechServcServcInfo` | 계약현황에 대한 기술용역서비스정보조회 | `untyCntrctNo`* | 12 | 검색조건에 통합계약번호를 입력하여 기술용역서비스정보(통합계약번호, 대표여부, 업종명, 공사현장지역명, 공사금액) 조회 |
| 14 | `getCntrctInfoListServcPPSSrch` | 나라장터검색조건에 의한 계약현황 용역조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `insttDivCd`, `insttClsfcCd`, `insttCd`, `insttNm`, `cnsttyNm`, `cntrctNm`, `cntrctMthdCd`, `cntrctRefNo`, `cntrctDivCd`, `dcsnCntrctNo`, `reqNo`, `ntceNo` | 47 | 나라장터 검색조건인 계약체결일자, 확정계약번호, 요청번호, 공고번호, 기관분류(계약기관), 기관명, 공종명, 계약명, 계약방법, 계약참조번호를 입력하면 용역계약정보(통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코 |
| 15 | `getCntrctInfoListServcChgHstry` | 계약현황에 대한 용역변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 42 | 검색조건인 변경일자, 통합계약번호를 입력하면 용역 계약변경이력정보(통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계약기관소관구분명, 계약기관담당부서명, 계약기관담당자명, 계약기관담당자전화번호,  |
| 16 | `getCntrctInfoListServcDltHstry` | 계약현황에 대한 용역삭제이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 12 | 검색조건에 삭제일시, 통합계약번호를 입력하여 용역 계약삭제이력정보( 삭제일시, 변경구분명, 통합계약번호, 확정계약번호, 계약참조번호) 조회 |
| 17 | `getCntrctInfoListFrgcpt` | 계약현황에 대한 외자조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 40 | 검색조건을 등록일시, 통합계약번호 등을 입력하여 외자 계약현황 (통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계약기관소관구분명, 계약기관담당부서명, 계약기관담당자명, 계약기관담당자전화번호, 계 |
| 18 | `getCntrctInfoListFrgcptDetail` | 계약현황에 대한 외자세부조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 26 | 검색조건을 계약체결일시, 통합계약번호 등을 입력하여 외자 계약세부현황 (계약체결일자, 통합계약번호, 확정계약번호, 계약참조번호, 부가물품분류번호, 물품분류번호, 물품식별번호, 품명, 한글품목명, 원산지코드, 원산지명, 수량단가금액, 물품수량, 물품금액, 물품금액통화, 인도조건코드, 인도조건명, 납품일수, 납품기한) 정보를 조회 |
| 19 | `getCntrctInfoListFrgcptPPSSrch` | 나라장터검색조건에 의한 계약현황 외자조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `insttDivCd`, `insttClsfcCd`, `insttCd`, `insttNm`, `prdctClsfcNoNm`, `cntrctRefNo`, `splyCorpNm`, `makeCorpNm`, `dcsnCntrctNo`, `reqNo`, `ntceNo` | 40 | 나라장터 검색조건인 계약체결일자, 공급자, 제작사, 공고번호, 기관분류 (계약기관), 기관명, 품명, 계약방법, 계약참조번호를 입력하면 외자계약현황(통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코드, 계약기관명, |
| 20 | `getCntrctInfoListFrgcptChgHstry` | 계약현황에 대한 외자변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 39 | 검색조건을 변경일시, 통합계약번호 등을 입력하여 외자 계약변경이력 (통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 장기계속구분명, 계약체결일자, 계약기간, 근거법률명, 총계약금액, 금차계약금액, 보증금률, 계약정보URL, 지급구분명, 요청번호, 공고번호, 계약기관코드, 계약기관명, 계약기관소관구분명, 계약기관담당부서명, 계약기관담당자명, 계약기관담당자전화번호, |
| 21 | `getCntrctInfoListFrgcptDltHstry` | 계약현황에 대한 외자삭제이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 12 | 검색조건에 삭제일시, 통합계약번호를 입력하여 외자 계약삭제이력정보( 삭제일시, 변경구분명, 통합계약번호, 확정계약번호, 계약참조번호) 조회 |

## 계약과정통합 — 나라장터 계약과정통합공개서비스 (15129459)

- 서비스 ID `CntrctProcssIntgOpenService` · 오퍼레이션 4개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getCntrctProcssIntgOpenFrgcpt` | 계약과정통합공개정보에 대한 외자조회 | `inqryDiv`*, `bidNtceNo`, `bidNtceOrd`, `bfSpecRgstNo`, `orderPlanNo`, `prcrmntReqNo` | 26 | 사용자가 [입찰공고번호,사전규격등록번호,발주계획번호,조달요청번호] 중 한 번호를 알고 있는 경우 해당 외자입찰공고의 업무 진행과정(발주계획번호,사업명,발주기관명,사전규격등록번호,입찰공고명,낙찰업체명,낙찰금액,낙찰률,계약번호,계약건명 등)을 조회 단, 입찰공고번호는 입찰공고차수를 입력하지 않아도 관련 공고 정보조회 가능 |
| 2 | `getCntrctProcssIntgOpenThng` | 계약과정통합공개정보에 대한 물품조회 | `inqryDiv`*, `bidNtceNo`, `bidNtceOrd`, `bfSpecRgstNo`, `orderPlanNo`, `prcrmntReqNo` | 26 | 사용자가 [입찰공고번호,사전규격등록번호,발주계획번호,조달요청번호] 중 한 번호를 알고 있는 경우 해당 물품입찰공고의 업무 진행과정(발주계획번호,사업명,발주기관명,사전규격등록번호,입찰공고명,낙찰업체명,낙찰금액,낙찰률,계약번호,계약건명 등)을 조회 단, 입찰공고번호는 입찰공고차수를 입력하지 않아도 관련 공고 정보조회 가능 |
| 3 | `getCntrctProcssIntgOpenServc` | 계약과정통합공개정보에 대한 용역조회 | `inqryDiv`*, `bidNtceNo`, `bidNtceOrd`, `bfSpecRgstNo`, `orderPlanNo`, `prcrmntReqNo` | 26 | 사용자가 [입찰공고번호,사전규격등록번호,발주계획번호,조달요청번호] 중 한 번호를 알고 있는 경우 해당 용역입찰공고의 업무 진행과정(발주계획번호,사업명,발주기관명,사전규격등록번호,입찰공고명,낙찰업체명,낙찰금액,낙찰률,계약번호,계약건명 등)을 조회 단, 입찰공고번호는 입찰공고차수를 입력하지 않아도 관련 공고 정보조회 가능 |
| 4 | `getCntrctProcssIntgOpenCnstwk` | 계약과정통합공개정보에 대한 공사조회 | `inqryDiv`*, `bidNtceNo`, `bidNtceOrd`, `bfSpecRgstNo`, `orderPlanNo`, `prcrmntReqNo` | 26 | 사용자가 [입찰공고번호,사전규격등록번호,발주계획번호,조달요청번호] 중 한 번호를 알고 있는 경우 해당 공사입찰공고 업무 진행과정(발주계획번호,사업명,발주기관명,사전규격등록번호,입찰공고명,낙찰업체명,낙찰금액,낙찰률,계약번호,계약건명 등)을 조회 단, 입찰공고번호는 입찰공고차수를 입력하지 않아도 관련 공고 정보조회 가능 |

## 쇼핑몰 — 나라장터 쇼핑몰 품목정보 서비스 (15129471)

- 서비스 ID `ShoppingMallPrdctInfoService` · 오퍼레이션 9개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getMASCntrctPrdctInfoList` | 다수공급자계약 품목정보 조회 | `rgstDtBgnDt`, `rgstDtEndDt`, `prdctClsfcNoNm`, `prdctIdntNo`, `cntrctCorpNm`, `chgDtBgnDt`, `chgDtEndDt`, `prodctCertYn` | 93 | 나라장터 쇼핑몰의 다수공급자계약 품목정보(계약정보, 업체정보, 규격서첨부파일) 등을 조회. 단, 거래정지 및 해지 건은 제공되지 않음  다수공급자계약이란 각 공공기관의 다양한 수요를 충족하기 위하여 품질, 성능, 효율 등에서 동등하거나 유사한 종류의 물품을 수요기관이 선택할 수 있도록 2인 이상을 계약상대자로 하는 계약방법으로 납품실적, 경영상태 등이 일정한 기준에 적합한 자를 대상으로 협상 |
| 2 | `getUcntrctPrdctInfoList` | 일반단가계약 품목정보 조회 | `rgstDtBgnDt`, `rgstDtEndDt`, `prdctClsfcNoNm`, `prdctIdntNo`, `cntrctCorpNm`, `chgDtBgnDt`, `chgDtEndDt`, `prodctCertYn` | 93 | 나라장터 쇼핑몰의 일반단가계약 품목정보(계약정보, 업체정보, 규격서첨부파일) 등을 조회. 단, 거래정지 및 해지 건은 제공되지 않음  일반단가계약은 다수 기관에서 공통적으로 사용하고 수요빈도가 많은 품목에 대하여 단가에 의하여 입찰 및 수의시담 하고 예정 수량을 명시하여 체결하는 계약[국가계약법 제22조]방법으로 단가계약물품은 정형화된 규격에 의하여 제조∙공급되는 물품. (철근, 시멘트, 레 |
| 3 | `getThptyUcntrctPrdctInfoList` | 제3자단가계약 품목정보 조회 | `rgstDtBgnDt`, `rgstDtEndDt`, `prdctClsfcNoNm`, `prdctIdntNo`, `cntrctCorpNm`, `chgDtBgnDt`, `chgDtEndDt`, `prodctCertYn` | 93 | 나라장터쇼핑몰의 제3자단가계약 품목정보(계약정보, 업체정보, 규격서첨부파일) 등을 조회. 단, 거래정지 및 해지 건은 제공되지 않음  제3자단가계약이란 수요기관에서 공통적으로 소요되고 신속공급이 필요한 물자의 제조∙구매 및 가공등의 계약에 관하여 미리 단가만을 정하여 공고하고 각 수요기관에서 계약상대자에게 직접 납품요구하여 구매하는 계약[조달사업에관한법률 제5조, 동법 시행령 제7조]방법으로 |
| 4 | `getDlvrReqInfoList` | 나라장터쇼핑몰 납품요구정보 현황 목록조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `dlvrReqNo`, `cntrctNo`, `dminsttCd`, `dminsttNm` | 35 | 납품요구는 단가계약(일반단가, 제3자단가, 다수공급자계약)으로 체결후 나라장터쇼핑몰에 등록 된 물품을 수요기관이 계약업체에 해당 물품을 납품할 것을 요청하며 조달청은 납품요구서를 계약업체에 발행하여 납품기한 이내에 납품을 업무로 검색조건을 납품요구접수일자, 납품요구번호, 계약번호를 통해 납품요구서의 정보를 조회 * 수요기관이 나라장터쇼핑몰에서 납품요구한 정보 제공 *현재일로부터 납품요구접수일 |
| 5 | `getDlvrReqDtlInfoList` | 나라장터쇼핑몰 납품요구상세 현황 목록조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `dlvrReqNo`, `cntrctNo`, `prdctClsfcNoNm`, `dtilPrdctClsfcNoNm`, `prdctIdntNoNm` | 44 | 납품요구정보의 물품 세품 납품요구내역으로 검색조건을 납품요구접수일자, 납품요구번호, 계약번호 , 물품분류명, 세부품명, 품목명을통해 납품요구 물품의 세부 정보를 조회 * 수요기관이 나라장터 나라장터쇼핑몰에서 납품요구한 물품의 세부정보 제공 *현재일로부터 납품요구접수일자 하루전 데이터 제공 |
| 6 | `getShoppingMallPrdctInfoList` | 나라장터쇼핑몰 품목 정보 목록 조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `prdctClsfcNoNm`, `dtilPrdctClsfcNoNm`, `prdctIdntNoNm`, `exclcProdctYn`, `masYn`, `prodctCertYn`, `shopngCntrctNo`*, `regtCncelYn` | 38 | 나라장터쇼핑몰에 등록된 품목을 검색조건을 등록일자,물품분류명,세부물품분류명,식별명을 통해 품목정보를 조회 *현재일로부터 등록일자 하루전 데이터 제공 |
| 7 | `getVntrPrdctOrderDealDtlsInfoList` | 벤처나라 물품 주문거래 내역 조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `prdctClsfcNoNm`, `dtilPrdctClsfcNoNm`, `prdctIdntNoNm`, `dminsttNm`, `dminsttRgnNm` | 19 | 벤처나라 거래물품 정보 및 주문 실적, 기관 소재지 창업·벤처기업 물품 거래현황 제공  *현재일로부터 등록일자 하루전 데이터 제공 |
| 8 | `getSpcifyPrdlstPrcureInfoList` | 특정품목조달내역 목록 조회 | `inqryDiv`*, `inqryBgnDate`*, `inqryEndDate`*, `inqryPrdctDiv`*, `prdctClsfcNo`, `prdctClsfcNoNm`, `dtilPrdctClsfcNo`, `dtilPrdctClsfcNoNm`, `prdctIdntNo`, `prdctIdntNoNm`, `prcrmntDiv`, `dminsttcD`, `dminsttNm`, `bizRegNo`, `corpNm`, `fnlCntrctDlvrReqChgOrdYn`, `dmndInsttDivCd`, `dminsttRgnNm`, `cntrctMthdCd`, `exclcProdctYn`, `cnstwkMtrlDrctPurchsObjYn` | 43 | 나라장터 총액계약 및 납품요구 구매실적 정보를 특정물품정보를 통해 물품.일반용역의 현황 제공  *현재일로부터 등록일자 하루전 데이터 제공 |
| 9 | `getSpcifyPrdlstPrcureTotList` | 특정품목조달집계 목록 조회 | `inqryDiv`*, `inqryBgnDate`*, `inqryEndDate`*, `inqryPrdctDiv`*, `prdctClsfcNo`, `prdctClsfcNoNm`, `dtilPrdctClsfcNo`, `dtilPrdctClsfcNoNm`, `prdctIdntNo`, `prdctIdntNoNm`, `prcrmntDiv`, `cntrctDlvrDiv`, `dminsttCd`, `dminsttNm`, `bizno`, `corpNm`, `fnlCntrctDlvrReqChgOrdYn`, `dmndInsttDivCd`, `dminsttRgnNm`, `cntrctMthdCd`, `exclcProdctYn`, `cnstwkMtrlDrctPurchsObjYn` | 27 | 나라장터 총액계약 및 납품요구 구매실적 정보를 특정물품정보를 통해 물품.일반용역의 가격에  대한 조달 집계 *현재일로부터 등록일자 하루전 데이터 제공 |

## 사용자 — 나라장터 사용자정보서비스 (15129466)

- 서비스 ID `UsrInfoService02` · 오퍼레이션 5개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getDminsttInfo02` | 수요기관정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `dminsttCd`, `dminsttNm`, `bizno` | 33 | 수요기관코드, 사업자등록번호, 수요기관명을 입력하여 수요기관명, 유효기간,법인등록번호, 사업자등록번호, 소관구분명, 기관유형명, 업태명, 업종명, 주소,등록일시 등 수요기관정보 목록을 조회. |
| 2 | `getPrcrmntCorpBasicInfo02` | 조달업체 기본정보 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `corpNm`, `bizno` | 28 | 검색조건에 사업자등록번호와 업체명을 입력하여 사업자등록번호, 업체명, 영문업체명, 개업일시, 지역코드, 지역명, 우편번호, 주소, 상세주소, 전화번호, 팩스번호, 국가명, 홈페이지주소, 제조구분코드, 제조구분명, 종업원수, 업체업무구분코드, 업체업무구분명, 본사구분명, 등록일시, 변경일시, 고유번호증명등록여부, 대표자명 등 조달업체 기본정보 목록을 조회. |
| 3 | `getPrcrmntCorpIndstrytyInfo02` | 조달업체업종정보조회 | `inqryDiv`*, `bizno`, `inqryBgnDt`, `inqryEndDt` | 15 | 검색조건에 사업자등록번호를 입력하여 사업자등록번호, 업종코드, 업종명, 등록일시, 유효기간만료일시, 시스템등록일시, 변경일시, 업종상태명, 대표업종여부 등 조달업체 업종정보 목록을 조회. |
| 4 | `getPrcrmntCorpSplyPrdctInfo02` | 조달업체공급물품정보조회 | `inqryDiv`*, `bizno`, `inqryBgnDt`, `inqryEndDt` | 12 | 검색조건에 사업자등록번호를 입력하여 사업자등록번호, 세부품명, 세부품명번호, 등록일시, 변경일시, 대표품명여부 등 조달업체 공급물품정보 목록을 조회. |
| 5 | `getUnptRsttCorpInfo02` | 부정당재제업체정보조회 | `inqryDiv`*, `bizno`, `inqryBgnDt`, `inqryEndDt` | 22 | 부정당 제재 업체 정보를 사업자등록번호, 재재시작일자 검색조건으로 사업자등록번호, 업체명,법인등록번호, 제재시작일자, 재재종료일자, 재재기관명, 계약법구분,제재근거법률,조항호, 조항호코드, 조항호코드명,시행규칙코드, 시행규칙코드명 목록을 조회. (나라장터미등록업체 , 개인에 대한 부정당제재는 미제공) [국가계약법] –조회시점에 제재만료,해제된 것은 제공되지 않습니다. [지방계약법]-조회시점에 |

## 물품목록 — 조달청 물품목록정보서비스 (15129417)

- 서비스 ID `ThngListInfoService02` · 오퍼레이션 13개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getThngGuidanceMapInfo02` | 목록정보(일반검색) 물품안내지도 조회 | `upPrdctClsfcNo` | 12 | 상위 물품분류번호로 검색을 하면 목록정보시스템(일반검색)에서 상위 물품분류번호에 속하는 하위 물품분류번호, 품명, 물품분류관련 설명 등이 조회된다. ▶최상위물품분류ID(upPrdctClsfcNo)가 "root"이며 이 조건으로 조회시 2단위 물품분류번호가 조회됩니다.  2단위의 물품분류ID가 4단위 물품분류번호의 상위 물품분류번호가 됩니다.  ex) [1010 : 산동물]의 상위물품번호는 [ |
| 2 | `getThngPrdnmLocplcAccotListInfoInfoPrdlstSearch02` | 목록정보(일반검색) 품목 목록 조회 | `dtilPrdctClsfcNo`, `prdctIdntNo`, `prdctClsfcNoEngNm`, `prdctClsfcNoNm`, `krnPrdctNm`, `inqryBgnDt`, `inqryEndDt`, `chgPrdBgnDt`, `chgPrdEndDt` | 22 | 목록정보(일반검색) 품목 목록 조회의 검색조건(세부품명번호,물품식별번호,품명 등)을 입력하면 물품이미지(대),물품분류번호,물품식별번호,세부품명번호,품명,영문품명,한글품목명,삭제유무,사용여부,조달업체등록번호,제조업체명 등 조회된다 ▶ 입력변수가 하나라도 있어야 데이터 조회 됨 |
| 3 | `getThngPrdnmLocplcAccotListInfoInfoPrdnmSearch02` | 목록정보(일반검색) 품명 목록 조회 | `prdctClsfcNo`, `dtilPrdctClsfcNo`, `prdctClsfcNoEngNm`, `prdctClsfcNoNm` | 13 | 목록정보(일반검색) 품명 목록 조회의 검색조건(물품분류번호, 세부품명번호,영문품명, 품명)을 입력하면 물품분류번호,품명,영문품명,세부품명번호 등 조회된다 |
| 4 | `getThngPrdnmLocplcAccotListInfoInfoLocplcSearch02` | 목록정보(일반검색) 소재지 목록 조회 | `dtilPrdctClsfcNo`, `prdctIdntNo`, `mnfctCorpNm`, `krnPrdctNm`, `rgnCd` | 19 | 목록정보(일반검색) 소재지 목록조회의 검색조건(세부품명번호, 물품식별번호,제조업체명, 제조업체의 지역코드 등)을 입력하면 물품분류번호,품명,영문품명,세부품명번호,지역코드 등 조회된다 |
| 5 | `getThngListClChangeHistInfo02` | 목록정보(일반검색) 분류변경이력 조회 | `inqryDiv`*, `prdctClsfcNo`, `inqryBgnDt`, `inqryEndDt` | 15 | 목록정보(일반검색) 분류변경이력 조회의 검색조건(현재 물품분류번호)을 입력하면 변경전후물품분류번호,변경전후품명 등 물품분류변경 이력이 조회된다 |
| 6 | `getLsfgdNdPrdlstChghstlnfoSttus02` | 목록정보(일반검색) 품목변경이력 조회 | `inqryDiv`*, `prdctIdntNo`, `inqryBgnDt`, `inqryEndDt` | 12 | 목록정보(일반검색) 품목변경이력 조회의 검색조건(물품식별번호)을 입력하면 변경전후물품분류번호,변경전후품명,변경전물품속성값 등 품목변경이력이 조회된다 |
| 7 | `getPrdctClsfcNoUnit2Info02` | 물품분류2단위 내역조회 | `prdctClsfcNoBgnNo`, `prdctClsfcNoEndNo`, `prdctClsfcNoNm`, `prdctClsfcNoEngNm` | 11 | 물품분류2단위 내역조회의 검색조건(물품분류번호시작번호, 물품분류번호종료번호,품명,영문품명)을 입력하면 물품분류번호(2단위),품명(2단위),영문품명(2단위),품명해설 등이 조회된다  ▶ 조달청 물품분류번호는 대분류(Segment) - 중분류(Family) - 소분류(Class) - 세분류(Commodity) 4단계의 계층구조로 구성되며, 각 단계별 2자리의 코드를 가지고 있는 총 8자리의 번호 |
| 8 | `getPrdctClsfcNoUnit4Info02` | 물품분류4단위 내역조회 | `prdctClsfcNoBgnNo`, `prdctClsfcNoEndNo`, `prdctClsfcNoNm`, `prdctClsfcNoEngNm` | 11 | 물품분류4단위 내역조회의 검색조건(물품분류번호시작번호, 물품분류번호종료번호, 품명,영문품명 )을 입력하면 물품분류번호(4단위),품명(4단위),영문품명(4단위),품명해설 등이 조회된다  ▶ 조달청 물품분류번호는 대분류(Segment) - 중분류(Family) - 소분류(Class) - 세분류(Commodity) 4단계의 계층구조로 구성되며, 각 단계별 2자리의 코드를 가지고 있는 총 8자리의  |
| 9 | `getPrdctClsfcNoUnit6Info02` | 물품분류6단위 내역조회 | `prdctClsfcNoBgnNo`, `prdctClsfcNoEndNo`, `prdctClsfcNoNm`, `prdctClsfcNoEngNm` | 11 | 물품분류6단위 내역조회의 검색조건(물품분류번호시작번호,물품분류번호종료번호,품명,영문품명)을 입력하면 물품분류번호(6단위),품명(6단위),영문품명(6단위),품명해설 등이 조회된다  ▶ 조달청 물품분류번호는 대분류(Segment) - 중분류(Family) - 소분류(Class) - 세분류(Commodity) 4단계의 계층구조로 구성되며, 각 단계별 2자리의 코드를 가지고 있는 총 8자리의 번호로 |
| 10 | `getPrdctClsfcNoUnit8Info02` | 물품분류8단위 내역조회 | `prdctClsfcNoBgnNo`, `prdctClsfcNoEndNo`, `prdctClsfcNoNm`, `prdctClsfcNoEngNm` | 11 | 물품분류8단위 내역조회의 검색조건(물품분류번호시작번호, 물품분류번호종료번호, 품명,영문품명)을 입력하면 물품분류번호,품명영문품명,품명해설 등이 조회된다  ▶ 조달청 물품분류번호는 대분류(Segment) - 중분류(Family) - 소분류(Class) - 세분류(Commodity) 4단계의 계층구조로 구성되며, 각 단계별 2자리의 코드를 가지고 있는 총 8자리의 번호로 되어 있으며 물품분류8단 |
| 11 | `getPrdctClsfcNoUnit10Info02` | 물품분류10단위 내역조회 | `dtilPrdctClsfcNoBgnNo`, `dtilPrdctClsfcNoEndNo`, `dtilPrdctClsfcNoNm`, `dtilPrdctClsfcNoEngNm` | 11 | 물품분류10단위 내역조회의 검색조건(물품분류번호시작번호, 물품분류번호종료번호, 품명, 영문품명)을 입력하면 세부품명번호,세부품명,세부영문품명,세부품명해설,사용여부 등이 조회된다  ▶ 물품분류번호10단위는 세부품명번호로 세분류(Commodity)의 품명보다 세분화가 필요한 품명을 세부품명으로 분류하며, 이에 대응하는 세부품명번호는 물품분류번호 다음에 2자리를 추가하여 10자리 숫자로 이루어짐  |
| 12 | `getPrdctClsfcNoChgHstry02` | 물품분류변경 이력조회 | `chgPrdBgnDt`*, `chgPrdEndDt`*, `prdctClsfcNo` | 17 | 물품목록분류(물품분류2단위, 4단위, 6단위, 8단위) 변경이력조회의 검색조건(변경기간시작일자,변경기간종료일자,물품분류번호)을 입력하면 물품분류번호,품명, 변경전후물품분류번호,변경전후물품분류번호명, 변경사유내용 등이 조회된다 |
| 13 | `getPrdctIndvAtrbInfoList02` | 품목개별속성정보 조회 | `prdctIdntNo`* | 11 | 품목(물품식별)정보에 해당되는 개별 속성 및 속성값 , 측정단위 정보 제공 |

## 물품관리 — 조달청 물품관리정보서비스 (15129470)

- 서비스 ID `PrdctMngInfoService` · 오퍼레이션 1개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPrdctClsfcNoUslfsvc` | 물품분류번호별 내용연수조회 | `prdctClsfcNoBgnNo`, `prdctClsfcNoEndNo`, `prdctClsfcNoNm` | 11 | 조달청에서 고시하는 물품분류번호별 내용연수(service life, 견적된 가능 연수)를 제공하는 오퍼레이션으로 검색조건(물품분류번호시작번호, 물품분류번호종료번호, 품명)을 입력하면 물품분류번호, 품명, 내용년수, 등록일자 등이 조회된다 ▶ 조건 입력을 하지 않을 경우 전체 조회 |

## 업종법규 — 나라장터 업종 및 근거법규서비스 (15129467)

- 서비스 ID `IndstrytyBaseLawrgltInfoService` · 오퍼레이션 1개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getIndstrytyBaseLawrgltInfoList` | 업종 및 근거법규 정보 조회 | `indstrytyClsfcCd`, `indstrytyNm`, `indstrytyCd`, `inqryBgnDt`, `inqryEndDt`, `indstrytyUseYn` | 17 | 업종 및 근거법규 정보 목록을 조회할 수 있다. - 조건 입력을 하지 않을 경우 전체 조회 |

## 가격 — 나라장터 가격정보현황서비스 (15129415)

- 서비스 ID `PriceInfoService` · 오퍼레이션 11개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPriceInfoListFcltyCmmnMtrilEngrk` | 시설공통자재(토목) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시설공통자재(토목) 가격정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,가격 등 조회. |
| 2 | `getPriceInfoListFcltyCmmnMtrilBildng` | 시설공통자재(건축) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시설공통자재(건축) 가격정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,가격 등 조회 |
| 3 | `getPriceInfoListFcltyCmmnMtrilMchnEqp` | 시설공통자재(기계설비) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시설공통자재(기계설비) 가격정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,가격 등 조회 |
| 4 | `getPriceInfoListFcltyCmmnMtrilElctyIrmc` | 시설공통자재(전기, 정보통신) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시설공통자재(전기,정보통신) 가격정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,가격 등 조회 |
| 5 | `getPriceInfoListMrktCnstrctPcEngrk` | 시장시공가격(토목) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시장시공가격(토목) 정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,시장시공가격 등 조회 |
| 6 | `getPriceInfoListMrktCnstrctPcBildng` | 시장시공가격(건축) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시장시공가격(건축) 정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,시장시공가격 등 조회 |
| 7 | `getPriceInfoListMrktCnstrctPcMchnEqp` | 시장시공가격(기계설비) 가격정보 | `prdctClsfcNo`, `prdctClsfcNoNm`, `prdctIdntNo`, `krnPrdctNm` | 28 | 시장시공가격(기계설비) 정보의 검색조건(물품분류번호, 품명, 물품식별번호, 규격명)을 입력하면 물품분류번호, 관련부서정보, 관련계약정보, 시장시공가격 등 조회 |
| 8 | `getCnsttyClsfcInfoList` | 공종분류및세부공종 |  | 28 | 시설공사공종분류 검색조건(공사분류코드)을 입력하면 수량산출공종분류코, 수량산출코드명 등 조회. |
| 9 | `getStdMarkUprcinfoList` | 표준시장단가및시장시공가격 정보 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate` | 17 | 시설공사 표준시장단가 공사구분(토목,건축,전기,통신,설비) 발표일에 구성된 세부공종, 품명, 규격,단위, 재료비,노무비,경비 합계 |
| 10 | `getNetRsceinfoList` | 자원분류및순수자원 |  | 28 | 조달청 시설공사 가격조사 및 관리업무 규정에 따라 자원분류 및 순수자원을 정기적으로 가격을 조사한 자료 |
| 11 | `getPriceInfoListFcltyCmmnMtrilTotal` | 시설공통자재(종합) 가격정보 | `inqryDiv`*, `inqryBgnDate`*, `inqryEndDate`* | 28 | 시설공통자재(토목, 건축, 기계설비, 전기·정보통신) 가격정보의 검색조건(물품분류번호,품명,물품식별번호,규격명)을 입력하면 물품분류번호,관련부서정보,관련계약정보,가격 등 조회. |

## 통계 — 공공조달통계정보서비스 (15129412)

- 서비스 ID `PubPrcrmntStatInfoService` · 오퍼레이션 14개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getTotlPubPrcrmntSttus` | 전체 공공조달 현황 | `srchBssYear` | 12 | 검색조건에 기준년도를 입력하여 기준년월, 공급집계금액 등 전체 공공조달 현황을 조회 |
| 2 | `getInsttDivAccotPrcrmntSttus` | 기관구분별 조달 현황 | `srchBssYmBgn`, `srchBssYmEnd` | 30 | 검색조건에 기준년도범위를 입력하여 기준년도, 기준월, 통계구분명, 실적합계건수, 실적합계금액, 국가기관실적건수, 국가기관실적금액, 지방자치단체실적건수, 지방자치단체실적금액, 교육행정기관실적건수, 교육행정기관실적금액, 공기업실적건수, 공기업실적금액 등 기관구분별 조달 현황(을)를 조회 |
| 3 | `getEntrprsDivAccotPrcrmntSttus` | 기업구분별 조달 현황 | `srchBssYmBgn`, `srchBssYmEnd` | 22 | 검색조건에 기준년월 범위를 입력하여 기준년도, 기준월, 통계구분명, 실적합계건수, 실적합계금액, 대기업실적건수, 대기업실적금액, 중견기업실적건수, 중견기업실적금액, 중소기업실적건수, 중소기업실적금액, 외국기업실적건수, 외국기업실적금액, 기타실적건수, 기타실적금액, 미분류실적건, 미분류실적금액 등 기업구분별 조달 현황(을)를 조회 |
| 4 | `getCntrctMthdAccotSttus` | 계약방법별 현황 | `srchBssYmBgn`, `srchBssYmEnd` | 20 | 검색조건에 기준년월범위를 입력하여 기준년도, 기준월, 통계구분명, 실적합계건수, 실적합계금액, 일반경쟁실적건수, 일반경쟁실적금액, 제한경쟁실적건수, 제한경쟁실적금액, 지명경쟁실적건수, 지명경쟁실적금액, 수의계약실적건수, 수의계약실적금액, 미분류실적건수, 미분류실적금액 등 계약방법별 현황(을)를 조회 |
| 5 | `getRgnLmtSttus` | 지역제한 현황 | `srchBssYmBgn`, `srchBssYmEnd` | 13 | 검색조건에 기준년월범위를 입력하여 기준년도, 기준월, 통계구분명, 계약총액,입찰계약총액, 미입찰계약총액, 지역제한총액, 지역제한총액비율 등 지역제한 현황을 조회 |
| 6 | `getRgnDutyCmmnCntrctSttus` | 지역의무공동계약 현황 | `srchBssYmBgn`, `srchBssYmEnd` | 13 | 검색조건에 기준년월범위를 입력하여 기준년도, 기준월, 통계구분명, 계약총액,입찰계약총액, 미입찰계약총액, 지역의무공동계약총액, 지역의무공동계약총액비율 등 지역의무공동계약 현황(을)를 조회 |
| 7 | `getPrcrmntObjectBsnsObjAccotSttus` | 조달목적물(업무대상)별 현황 | `srchBssYmBgn`, `srchBssYmEnd` | 20 | 검색조건에 기준년월범위를 입력하여 기준년도, 기준월, 통계구분명, 실적합계건수, 실적합계금액, 물품실적건수, 물품실적금액, 공사실적건수, 공사실적금액, 일반용역실적건수, 일반용역실적금액, 기술용역실적건수, 기술용역실적금액, 미분류실적건수, 미분류실적금액 등 조달목적물(업무대상)별 현황(을)를 조회 |
| 8 | `getDminsttAccotEntrprsDivAccotArslt` | 수요기관별 기업구분별 실적 | `srchBssYmBgn`*, `srchBssYmEnd`*, `dminsttCd`, `dminsttNm`, `lwrInsttArsltInclsnYn`, `linkSystmCd` | 22 | 검색조건에 기준년월범위, 수요기관코드, 수요기관명, 하위기관실적포함여부, 연계시스템코드을 입력하여 수요기관코드, 수요기관명, 실적합계건수, 실적합계금액, 대기업실적건수, 대기업실적금액, 중견기업실적건수, 중견기업실적금액, 중소기업실적건수, 중소기업실적금액, 외국기업실적건수, 외국기업실적금액, 기타실적건수, 기타실적금액, 미분류실적건수, 미분류실적금액 등 수요기관별 기업구분별 실적 (을)를 조 |
| 9 | `getDminsttAccotCntrctMthdAccotArslt` | 수요기관별 계약방법별 실적 | `srchBssYmBgn`, `srchBssYmEnd`, `dminsttCd`, `dminsttNm`, `lwrInsttArsltInclsnYn`, `linkSystmCd` | 22 | 검색조건에 기준년월범위, 수요기관코드, 수요기관명, 하위기관실적포함여부, 연계시스템코드을 입력하여 수요기관코드, 수요기관명, 실적합계건수, 실적합계금액, 일반경쟁실적건수, 일반경쟁실적금액, 제한경쟁실적건수, 제한경쟁실적금액, 지명경쟁실적건수, 지명경쟁실적금액, 수의계약실적건수, 수의계약실적금액, 미분류실적건수, 미분류실적금액, 수기등록실적건수, 수기등록실적금액 등 수요기관별 계약방법별 실적을 |
| 10 | `getDminsttAccotBsnsObjAccotArslt` | 수요기관별 업무대상별 실적 | `srchBssYmBgn`, `srchBssYmEnd`, `dminsttCd`, `dminsttNm`, `lwrInsttArsltInclsnYn`, `linkSystmCd` | 20 | 검색조건에 기준년월범위, 수요기관코드, 수요기관명, 하위기관실적포함여부, 연계시스템코드을 입력하여 수요기관코드, 수요기관명, 실적합계건수, 실적합계금액, 물품실적건수, 물품실적금액, 공사실적건수, 공사실적금액, 일반용역실적건수, 일반용역실적금액, 기술용역실적건수, 기술용역실적금액, 미분류실적건수, 미분류실적금액 등 수요기관별 업무대상별 실적을 조회 |
| 11 | `getDminsttAccotSystmTyAccotArslt` | 수요기관별 시스템유형별 실적 | `srchBssYmBgn`, `srchBssYmEnd`, `dminsttCd`, `dminsttNm`, `lwrInsttArsltInclsnYn`, `linkSystmCd` | 18 | 검색조건에 기준년월범위, 수요기관코드, 수요기관명, 하위기관실적포함여부, 연계시스템코드을 입력하여 수요기관코드, 수요기관명, 실적합계건수, 실적합계금액, 중앙조달실적건수, 중앙조달실적금액, 자체조달실적건수, 자체조달실적금액, 자체조달시스템실적건수, 자체조달시스템실적금액, 수기조달실적건수, 수기조달실적금액 등 수요기관별 시스템유형별 실적을 조회 |
| 12 | `getPrcrmntEntrprsAccotCntrctMthdAccotArslt` | 조달기업별 계약방법별 실적 | `srchBssYmBgn`*, `srchBssYmEnd`*, `corpUntyNo`, `corpNm`, `linkSystmCd` | 22 | 검색조건에 기준년월범위, 업체통합번호, 업체명, 연계시스템코드을 입력하여 업체통합번호, 업체명, 실적합계건수, 실적합계금액, 일반경쟁실적건수, 일반경쟁실적금액, 제한경쟁실적건수, 제한경쟁실적금액, 지명경쟁실적건수, 지명경쟁실적금액, 수의계약실적건수, 수의계약실적금액, 미분류실적건수, 미분류실적금액, 수기등록실적건수, 수기등록실적금액 등 조달기업별 계약방법별 실적을 조회 |
| 13 | `getPrcrmntEntrprsAccotBsnsObjAccotArslt` | 조달기업별 업무대상별 실적 | `srchBssYmBgn`*, `srchBssYmEnd`*, `corpUntyNo`, `corpNm`, `linkSystmCd` | 20 | 검색조건에 기준년월범위, 업체통합번호, 업체명, 연계시스템코드을 입력하여 업체통합번호, 업체명, 실적합계건수, 실적합계금액, 물품실적건수, 물품실적금액, 공사실적건수, 공사실적금액, 일반용역실적건수, 일반용역실적금액, 기술용역실적건수, 기술용역실적금액, 미분류실적건수, 미분류실적금액 등 조달기업별 업무대상별 실적을 조회 |
| 14 | `getPrdctIdntNoServcAccotArslt` | 품목 및 서비스별 실적 | `srchBssYmBgn`, `srchBssYmEnd`, `prdctClsfcNo`, `prdctClsfcNm`, `linkSystmCd` | 20 | 검색조건에 기준년월범위, 물품분류번호, 품명을 입력하여 물품분류번호, 품명,실적합계건수, 실적합계금액, 일반경쟁실적건수, 일반경쟁실적금액, 제한경쟁실적건수, 제한경쟁실적금액, 지명경쟁실적건수, 지명경쟁실적금액, 수의계약실적건수, 수의계약실적금액, 미분류실적건수, 미분류실적금액 등 품목 및 서비스별 실적을 조회 |

## 개방표준 — 나라장터 공공데이터개방표준서비스 (15058815)

- 서비스 ID `PubDataOpnStdService` · 오퍼레이션 3개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getDataSetOpnStdBidPblancInfo` | 데이터셋 개방표준에 따른 입찰공고정보 | `bidNtceBgnDt`*, `bidNtceEndDt`* | 58 | 검색조건을 입찰공고일시로 하여 입찰공고번호, 입찰공고차수, 나라장터공고여부, 입찰공고명, 입찰공고상태명, 입찰공고일자, 입찰공고시각, 업무구분명, 국제입찰여부 등 나라장터에 등록된 입찰공고정보 조회 |
| 2 | `getDataSetOpnStdScsbidInfo` | 데이터셋 개방표준에 따른 낙찰정보 | `bsnsDivCd`*, `opengBgnDt`*, `opengEndDt`* | 43 | 검색조건을 개찰일시, 업무구분명으로 입찰공고번호, 입찰공고차수, 입찰공고명, 업무구분명, 계약체결형태명, 계약체결방법명, 낙찰자결정방법명, 공고기관명, 공고기관코드 등 나라장터에 등록된 낙찰정보 조회 |
| 3 | `getDataSetOpnStdCntrctInfo` | 데이터셋 개방표준에 따른 계약정보 | `cntrctCnclsBgnDate`*, `cntrctCnclsEndDate`*, `insttDivCd`, `insttCd` | 49 | 검색조건을 계약체결일자로 계약번호, 통합계약번호, 계약차수, 계약명, 업무구분명, 계약체결형태명, 계약체결방법명, 장기계속구분명, 공동계약여부, 계약체결일자, 계약기간, 계약금액 등 나라장터에 등록된 계약정보 조회 |

## 민간입찰 — 누리장터 민간입찰공고서비스 (15129456)

- 서비스 ID `PrvtBidNtceService` · 오퍼레이션 10개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPrvtBidPblancListInfoServc` | 민간입찰공고정보에 대한 용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 76 | 검색조건을 조회구분, 등록일범위, 공고일범위, 개찰일범위, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가 |
| 2 | `getPrvtBidPblancListInfoThng` | 민간입찰공고정보에 대한 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 76 | 검색조건을 조회구분, 등록일범위, 공고일범위, 개찰일범위, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가 |
| 3 | `getPrvtBidPblancListInfoCnstwk` | 민간입찰공고정보에 대한 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 76 | 검색조건을 조회구분, 등록일범위, 공고일범위, 개찰일범위, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가 |
| 4 | `getPrvtBidPblancListInfoEtc` | 민간입찰공고정보에 대한 기타조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 75 | 검색조건을 조회구분, 등록일범위, 공고일범위, 개찰일범위, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가 |
| 5 | `getPrvtBidPblancListInfoLicenseLimit` | 민간입찰공고정보에 대한 면허제한정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 12 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 제한그룹번호, 제한순번, 면허제한명, 허용업종목록, 등록일시를 포함한 면허제한정보 조회 |
| 6 | `getPrvtBidPblancListInfoPrtcptPsblRgn` | 민간입찰공고정보에 대한 참가가능지역정보조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bidNtceOrd` | 10 | 검색조건에 등록일시범위(통합입찰공고)와 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 제한그룹번호, 참가가능지역명, 등록일시 등 참가가능지역정보조회 |
| 7 | `getPrvtBidPblancListInfoServcPPSSrch` | 나라장터 검색조건에 의한 민간입찰공고정보에 대한 용역조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 76 | 검색조건을 조회구분, 공고일시범위, 개찰일시범위를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가치세포함여부명, 기준금액 |
| 8 | `getPrvtBidPblancListInfoThngPPSSrch` | 나라장터 검색조건에 의한 민간입찰공고정보에 대한 물품조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 76 | 검색조건을 조회구분, 공고일시범위, 개찰일시범위를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가치세포함여부명, 기준금액 |
| 9 | `getPrvtBidPblancListInfoCnstwkPPSSrch` | 나라장터 검색조건에 의한 민간입찰공고정보에 대한 공사조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 76 | 검색조건을 조회구분, 공고일시범위, 개찰일시범위를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가치세포함여부명, 기준금액 |
| 10 | `getPrvtBidPblancListInfoEtcPPSSrch` | 나라장터 검색조건에 의한 민간입찰공고정보에 대한 기타조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `bidClseExcpYn`, `intrntnlDivCd` | 75 | 검색조건을 조회구분, 공고일시범위, 개찰일시범위를 입력하여 입찰공고번호, 입찰공고차수, 입찰공고분류, 게시일시, 참조번호, 공고명, 공고구분명, 공고기관명, 입찰방식명, 계약방법명, 낙찰방법명, 재입찰구분명, 입찰자격명, 담당자명, 담당자전화번호, 담당자이메일, 입찰개시일시, 입찰마감일시, 개찰일시, 개찰장소, 입찰보증서접수마감일시, 현장설명일시, 현장설명장소, 부가가치세포함여부명, 기준금액 |

## 민간낙찰 — 누리장터 민간낙찰정보서비스 (15129458)

- 서비스 ID `PrvtScsbidInfoService` · 오퍼레이션 7개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPrvtScsbidListSttus` | 민간 낙찰된 목록 현황 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`, `bsnsDivCd` | 20 | 검색조건에 조회구분, 조회시작일시, 조회종료일시, 입찰공고번호를 입력하여 업무구분코드 입찰공고번호, 입찰공고차수, 재입찰번호, 입찰공고명, 수요기관코드, 수요기관명, 실개찰일시, 참가업체수, 최종낙찰금액, 최종낙찰률, 최종낙찰업체명, 최종낙찰업체대표자명, 최종낙찰업체주소, 최종낙찰업체전화번호 등의 누리장터시스템에 등록된 낙찰 정보 조회 |
| 2 | `getPrvtOpengResultListInfo` | 민간 개찰결과 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo` | 16 | 검색조건에 조회구분, 조회시작일시, 조회종료일시, 입찰공고번호를 입력하여 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 입찰공고명, 수요기관코드, 수요기관명, 개찰일시, 참가업체수, 진행구분코드명, 개찰업체정보, 결과코드, 결과메세지, 한 페이지 결과 수, 페이지 번호, 데이터 총 개수, 입찰공고차수, 입찰분류번호, 재입찰번호, 입찰공고명, 수요기관코드, 수요기관명, 개찰일시, 참가 |
| 3 | `getPrvtScsbidListSttusPPSSrch` | 나라장터 검색조건에 의한 민간 낙찰된 목록 현황 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`*, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd` | 20 | 나라장터 검색조건으로 업무구분코드 입찰공고번호, 입찰공고차수, 재입찰번호, 입찰공고명, 수요기관코드, 수요기관명, 실개찰일시, 참가업체수, 최종낙찰금액, 최종낙찰률, 최종낙찰업체명, 최종낙찰업체대표자명, 최종낙찰업체주소, 최종낙찰업체전화번호 등의 누리장터시스템에 등록된 낙찰 정보 조회 |
| 4 | `getPrvtOpengResultListInfoPPSSrch` | 나라장터 검색조건에 의한 민간 개찰결과 목록 조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `bidNtceNo`*, `bidNtceNm`, `ntceInsttCd`, `ntceInsttNm`, `dminsttCd`, `dminsttNm`, `refNo`, `prtcptLmtRgnCd`, `prtcptLmtRgnNm`, `indstrytyCd`, `indstrytyNm`, `presmptPrceBgn`, `presmptPrceEnd`, `dtilPrdctClsfcNo`, `masYn`, `prcrmntReqNo`, `intrntnlDivCd` | 16 | 나라장터 검색조건을 입력하여 입찰공고번호, 입찰공고차수, 입찰분류번호, 재입찰번호, 입찰공고명, 수요기관코드, 수요기관명, 개찰일시, 참가업체수, 진행구분코드명, 개찰업체정보, 결과코드, 결과메세지, 한 페이지 결과 수, 페이지 번호, 데이터 총 개수, 입찰공고차수, 입찰분류번호, 재입찰번호, 입찰공고명, 수요기관코드, 수요기관명, 개찰일시, 참가업체수, 진행구분코드명, 개찰업체정보 등의 누 |
| 5 | `getPrvtOpengResultListInfoOpengCompt` | 민간 개찰결과 개찰완료 목록 조회 | `bidNtceNo`*, `bidNtceOrd`, `rbidNo` | 17 | 검색조건에 입찰공고번호, 입찰공고차수, 재입찰번호를 입력하여 개찰결과구분명, 입찰공고번호, 입찰공고차수, 재입찰번호, 개찰순위, 투찰업체사업자등록번호, 투찰업체명, 투찰업체대표자명, 투찰금액, 투찰률, 비고, 투찰일시등 개찰완료 정보를 조회 |
| 6 | `getPrvtOpengResultListInfoFailing` | 민간 개찰결과 유찰 목록 조회 | `bidNtceNo`*, `bidNtceOrd`, `rbidNo` | 10 | 검색조건에 입찰공고번호, 입찰공고차수, 재입찰번호를 입력하여 개찰결과구분명, 입찰공고번호, 입찰공고차수, 재입찰번호, 유찰사유 등 유찰 정보를 조회 |
| 7 | `getPrvtOpengResultListInfoRebid` | 민간 개찰결과 재입찰 목록 조회 | `bidNtceNo`*, `bidNtceOrd`, `rbidNo` | 11 | 검색조건에 입찰공고번호, 입찰공고차수, 재입찰번호를 입력하여 개찰결과구분명, 입찰공고번호, 입찰공고차수, 재입찰번호, 유찰사유 등 재입찰 정보를 조회 |

## 민간계약 — 누리장터 민간계약정보서비스 (15129469)

- 서비스 ID `PrvtCntrctInfoService` · 오퍼레이션 4개 · 갱신 수시

| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `getPrvtCntrctInfoList` | 계약현황 민간조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 31 | 검색조건을 등록일시, 통합계약번호로 하여 통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 계약체결일자, 계약기간, 총계약금액 등의 누리장터시스템에 등록된 계약 정보 조회 |
| 2 | `getPrvtCntrctInfoListPPSSrch` | 나라장터 검색조건에 의한 계약현황 민간조회 | `inqryDiv`*, `inqryBgnDate`, `inqryEndDate`, `insttCd`, `insttNm`, `cntrctNm`, `cntrctRefNo`, `cntrctNo`, `ntceNo` | 31 | 검색조건을 계약일자, 기관코드, 기관명, 계약번호, 공고번호로하여 통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 계약체결일자, 계약기간, 총계약금액 등의 누리장터시스템에 등록된 계약 정보 조회 |
| 3 | `getPrvtCntrctInfoListChgHstry` | 계약현황에 대한 민간변경이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 31 | 검색조건을 변경일시, 통합계약번호로 하여 통합계약번호, 업무구분명, 확정계약번호, 계약참조번호, 계약명, 공동계약여부, 계약체결일자, 계약기간, 총계약금액 등의 누리장터시스템에 등록된 계약변경정보 조회 |
| 4 | `getPrvtCntrctInfoListDltHstry` | 계약현황에 대한 민간삭제이력조회 | `inqryDiv`*, `inqryBgnDt`, `inqryEndDt`, `untyCntrctNo` | 10 | 검색조건에 삭제일시, 통합계약번호를 입력하여 민간 계약삭제이력정보(삭제일시, 변경구분명, 통합계약번호, 확정계약번호, 계약참조번호) 조회 |
