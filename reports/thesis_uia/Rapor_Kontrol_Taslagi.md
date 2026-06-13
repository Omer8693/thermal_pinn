# Rapor Kontrol Taslagi

Bu taslak, `thermal_pinn/reports/thesis_uia` altindaki mevcut tez dosyalari uzerinden hazirlanmistir. Hoca/TODO yorum satirlari bilerek degistirilmemistir.

## 1. Otomatik LaTeX Kontrolu

- Duplicate `\label{...}`: bulunmadi.
- Eksik `\ref{...}` / `\eqref{...}`: bulunmadi.
- Eksik citation: bulunmadi.
- Ana tez icin eksik figure: bulunmadi.
- `pdflatex` ve `latexmk` sistemde kurulu degil; bu nedenle tam PDF derleme testi yapilamadi.
- `visual_abstract/press_release.tex` ayri derlenirse `visual_abstract.png` path'i kendi klasor baglaminda dogru olmali. Ana tez `main.tex` icine dahil degil.

## 2. Yuksek Oncelikli Tutarsizliklar

### 2.1 Canonical benchmark threshold anlatimi tutarsiz

`method.tex` bolumunde canonical 2D/3D benchmarklar icin "no hard threshold is imposed" deniyor:

- `chapters/method.tex`, Engineering Acceptance Threshold bolumu: canonical 2D/3D icin hard threshold yok.

Ama results/discussion tarafinda canonical benchmarklar icin threshold dili kullaniliyor:

- `chapters/results_2d.tex`: tablo caption'i `within 10 C; grey = above threshold`.
- `chapters/results_3d.tex`: tablo caption'i `within 15 C; grey = above threshold`.
- `chapters/discussion.tex`: `On 2D benchmarks, all three architectures remain below the 10 C guideline through k=5.`

Oneri:

- Method bolumunu soyle netlestir:
  "Canonical 2D and 3D studies use 10 C and 15 C as reporting guidelines, not as hard acceptance thresholds. Thermal Fin uses 15 C as the explicit engineering acceptance threshold."
- Ya da results caption'larinda `threshold` yerine `reporting guideline` kullan.

### 2.2 Discussion 2D k=5 iddiasi tabloyla celisiyor

`chapters/discussion.tex` satir ~361:

- "On 2D benchmarks, all three architectures remain below the 10 C guideline through k=5."

Bu yanlis gorunuyor. `chapters/results_2d.tex` tablosuna gore:

- Circle 2D k=5:
  - Bayesian/TPE: 10.01 C
  - NSGA-II: 14.97 C
  - NSGA-III: 11.33 C
- L-Shape 2D k=5:
  - NSGA-II: 14.37 C
  - NSGA-III: 11.29 C

Oneri cumle:

"On 2D benchmarks, Bayesian/TPE remains within the 10 C guideline on Rectangle and L-Shape at k=5 and is only marginally above it on Circle, whereas the compact NSGA architectures exceed the guideline on the harder k=5 cases."

### 2.3 3D Rectangular NSGA-II aciklamasi tabloyla celisiyor

`chapters/results_3d.tex` satir ~87-89:

- "NSGA-II ... reaches L2=0.071 at k=5, coinciding with the MAE mean exceeding the 15 C threshold."

Ama `chapters/results_3d.tex` tablosunda Rectangular 3D NSGA-II k=5 MAE:

- `13.42 +/- 4.57 C`, yani 15 C altinda.

Oneri cumle:

"NSGA-II reaches L2=0.071 at k=5, slightly above the excellent L2 band, while its mean MAE remains below 15 C but with larger seed variance."

### 2.4 3D L-Shape NSGA-II sayisi yanlis gorunuyor

`chapters/results_3d.tex` satir ~147-148:

- "At k=5, NSGA-II degrades sharply (L2=0.094, sigma=0.025), consistent with the mean MAE exceeding 27 C."

Ama `chapters/results_3d.tex` tablosunda L-Shape 3D NSGA-II k=5:

- `15.65 +/- 8.85 C`.

Oneri:

- "exceeding 27 C" ifadesini kaynak tabloya gore duzelt.
- Eger 27 C baska bir per-window/final-window metriginden geliyorsa bu acikca belirtilmeli.

### 2.5 Fiziksel parametreler "same" diye fazla genellenmis

Su ifadeler tabloyla tam uyusmuyor:

- `chapters/discussion.tex`: "All domains use the same physical parameters from Mortensen..."
- `chapters/conclusion.tex`: "All domains used the physical parameters of Mortensen..."
- `chapters/method.tex`: "The same physical setup was used across all domain groups."

Ama parametre tablolarinda farklar var:

- Canonical 2D: `k_T=150`, `h=5000`.
- 2D adaptive: `k_T=160`, `h=5000`.
- 3D/Thermal Fin: `k_T=160`, `h=4000`.

Oneri cumle:

"All domains share the Mortensen-inspired quench setting, namely A356 aluminium, T0=540 C, Tw=20 C, and a 30-second quench. The simplified constant material and boundary parameters differ slightly between the 2D preliminary benchmarks and the 3D/Thermal Fin studies, as listed in Table ... ."

### 2.6 Conclusion seed variance iddiasi yanlis

`chapters/conclusion.tex` satir ~90-96:

- "Standard deviation remained below 0.9 C at k <= 4 across all domains."
- "At k=5 ... variance widened to roughly +/-0.5 C..."

Bu tablo degerleriyle celisiyor. Ornekler:

- `results_3d.tex`: Cylinder 3D NSGA-II k=4: `12.67 +/- 8.21 C`.
- `results_3d.tex`: Cylinder 3D NSGA-II k=5: `19.21 +/- 12.28 C`.
- `results_3d.tex`: L-Shape 3D NSGA-II k=5: `15.65 +/- 8.85 C`.

Oneri:

"Seed variance is small for the stable Bayesian/TPE configurations and for the 2D adaptive-k study, but it grows substantially for compact NSGA architectures on the harder 3D domains, especially Cylinder, Stacked Cubes, and L-Shape at high k."

### 2.7 "Bayesian/TPE best in 7 of 8 cases" net degil veya yanlis

`chapters/discussion.tex` satir ~315-319:

- "Bayesian/TPE achieved the lowest ten-seed mean MAE in 7 of 8 cases."

Bu ifade hangi `k` veya hangi summary metric icin gecerli oldugunu soylemiyor. 3D k=1 tablosunda Rectangular, Stacked ve L-Shape icin Bayesian/TPE en dusuk degil.

Oneri:

- Bu iddiayi belirli bir metrikle sinirla: "at the maximum useful skip factor", "on the fixed-k efficiency frontier", veya "in the headline deployment setting".
- Eger dogrulanamiyorsa daha temkinli yaz:
  "Bayesian/TPE provides the most robust accuracy-efficiency frontier, although compact NSGA models can outperform it at k=1 on selected 3D geometries."

### 2.8 PINN-only genellemesi fazla guclu

`chapters/discussion.tex` satir ~381-384:

- "PINN-only results demonstrate ... on all tested geometries."

Ama systematic PINN-only analysis esas olarak Thermal Fin uzerinde; 2D adaptive icin yalniz preliminary Square deneyi var.

Oneri:

"The Thermal Fin PINN-only study, supported by the preliminary 2D Square test, shows that removing FEM corrections causes severe error accumulation."

## 3. Orta Oncelikli Duzeltmeler

### 3.1 Methodology deney sayisi cumlesi daha net olmali

`chapters/method.tex` satir ~190-195:

- "We swept k=1,2,3,4,5 for all three architectures on all domains, giving 15 runs per domain group."

Bu ifade "per domain group" yerine "per domain before seeds" gibi okunmali. Ayrica adaptive 2D tarafinda transfer architecture da var.

Oneri:

"In fixed-k mode, each canonical domain was evaluated for three architectures and five skip factors, giving 15 architecture-k configurations per domain before random seeds."

### 3.2 `method.tex` Mortensen comparison table 2D farkini sakliyor

`chapters/method.tex` comparison table "This thesis" kolonunda `h=4000`, `k_T=160` diyor. Bu 3D/Thermal Fin icin dogru, fakat canonical 2D tarafinda `h=5000`, `k_T=150`.

Oneri:

- Tabloya "3D/Thermal Fin baseline" notu ekle.
- Ya da "constant h = 4000-5000 W/(m2K), depending on benchmark group" olarak yaz.

### 3.3 3D result paragraph'ta tekrarlanan satir

`chapters/results_3d.tex` satir ~155 iki kez ayni cumleyi baslatiyor:

- `Figure~\ref{fig:3d_bestk_fields} shows the predicted temperature field for`
- Aynisi tekrar ediyor.

Oneri:

- Bir tekrar satiri silinmeli.

### 3.4 Press release degree formatting

`visual_abstract/press_release.tex` icinde `2.5\,^\circ$C`, `5\,^\circ$C` gibi yazimlar var.

Oneri:

- Ana rapordaki gibi `$2.5\,^\circ\mathrm{C}$` formatina cek.

### 3.5 Visual abstract caption eski basliklari kullaniyor

`visual_abstract/press_release.tex` caption'i:

- "FEM reference solver, NAS-PINN framework, and MSWP strategy"

Visual abstract'taki Methodology basligi artik:

- "FEM Mesh & Solver · Single-Window Model · End-to-End Workflow · MSWP Modes"

Oneri:

- Caption'i yeni basliklarla uyumlu hale getir.

## 4. Iyi Durumda Olan Kisimler

- Abstract, Results ve Conclusion genel hikaye olarak uyumlu: 10 unique geometries, 8 canonical domains + adaptive 2D study mantigi korunuyor.
- 2D adaptive-k headline sonucu tutarli: 83--85% FEM saving, MAE < 2.5 C.
- Canonical 2D headline sonucu tutarli: Bayesian/TPE k=3 boyunca < 5 C.
- 3D headline sonucu genel olarak tutarli: Bayesian/TPE k=5 ile yaklasik < 14.1 C.
- Thermal Fin headline sonucu tutarli: Bayesian/TPE Fourier k=5 = 12.55 C; NSGA-II/III k=4'e kadar acceptable.
- Figure, label, citation altyapisi otomatik kontrolde temiz gorunuyor.

## 5. Onerilen Duzeltme Sirasi

1. Yuksek oncelikli sayisal celiskileri duzelt:
   - `results_3d.tex` Rectangular NSGA-II k=5 aciklamasi.
   - `results_3d.tex` L-Shape NSGA-II "27 C" ifadesi.
   - `discussion.tex` 2D k=5 10 C guideline cumlesi.
   - `conclusion.tex` seed variance maddesi.
2. Fiziksel parametre genellemelerini yumusat:
   - `discussion.tex`, `conclusion.tex`, `method.tex`.
3. Threshold/guideline terminolojisini tek standarda bagla.
4. Kucuk format/tekrar duzeltmeleri:
   - `results_3d.tex` duplicate line.
   - `press_release.tex` degree formatting and caption update.
5. Son adimda PDF derleme testi yap:
   - Bu ortamda `pdflatex`/`latexmk` yok; Overleaf veya TeX kurulu ortamda derleme kontrolu gerekli.

