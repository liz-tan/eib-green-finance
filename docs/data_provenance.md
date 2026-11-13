# Data provenance

## 1. EIB financed operations

**European Investment Bank, *Projects financed by the European Investment Bank*
("Multi-criteria list").** EIB Open Data.

- Browse: <https://www.eib.org/en/projects/loans/index.htm>
- Excel export endpoint:
  `https://www.eib.org/provider-eib-plr/app/loans/excel?sortColumn=loanParts.loanPartStatus.statusDate&sortDir=desc&pageNumber=0&itemPerPage=25&pageable=false&language=EN&defaultLanguage=EN&orLoanPartYearFrom=true&orLoanPartYearTo=true&orCountries.region=true&orCountries=true&orSectors=true`
- Mirror (EU Open Data Portal):
  <https://data.europa.eu/data/datasets/projects-financed-by-the-european-investment-bank>
- Basis: finance contracts signed. Coverage: 1959–2026. Format: Excel.
- Local file: `data/raw/loanExport.xlsx`.
- Accessed: November 2026. (Live dataset — updated as new contracts are signed.)

## 2. EIB Climate Action and Sustainability figures

**European Investment Bank, *Climate Action and Sustainability Figures*.**
EIB Public Register, document type "Climate and Environmental Sustainability".

- Register (filtered):
  `https://www.eib.org/en/registers/all/index?sortColumn=publicationDate&sortDir=desc&pageNumber=0&itemPerPage=10&pageable=true&la=EN&deLa=EN&orYearFrom=true&orYearTo=true&orDocumentLanguages=true&documentTypes=CLIMATEACTIONDATA&orDocumentTypes=true`
- Document access pattern:
  `https://www.eib.org/attachments/registers/<document-number>.<xlsx|pdf>`
- Documents retrieved (register numbers):
  - `282095787.xlsx`
  - `87461282.pdf`
  - `87468682.pdf`
  - `92782519.pdf`
  - `131122106.pdf`
  - `142790611.pdf`
  - `158964668.pdf`
  - `177005830.pdf`
  - `237189323.pdf`
  - `241849975.xlsx`
  - `253076121.xlsx`
- Basis: finance contracts signed. Format: Excel (recent years), PDF (earlier years).
- Local files: `data/raw/`.
- Accessed: November 2026.
