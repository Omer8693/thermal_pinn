# Thermal PINN Kod-Rapor Karşılaştırma Taslağı

Tarih: 2026-05-27

Bu taslak, `quenching_mswp` klasörü kapsam dışı bırakılarak hazırlanmıştır.
Bu klasör hoca onayı alınmadan teze eklenecek yeni çalışma olarak
kullanılmamalıdır. İnceleme yalnızca mevcut tez kaynakları, `checkpoints`,
`results/thermal_fin`, `results/fem_baseline`, `scripts`, `plots` ve raporda
referans verilen çıktılar üzerinden yapılmıştır. Amaç, rapordaki sonuç anlatımı
ile mevcut üretilmiş metrikler arasındaki eksikleri ve savunma öncesi
düzeltilmesi gereken noktaları toplamaktır.

## 1. İnceleme Kapsamı ve Sonuç Kaynakları

Bu revizyonda `thermal_pinn/quenching_mswp/` bilinçli olarak dışarıda
bırakıldı. O klasör yeni/ayrı çalışma kabul edilmeli ve danışman onayı olmadan
tez iddiasına bağlanmamalıdır.

Bu taslakta kullanılan kaynaklar:

- `thermal_pinn/checkpoints/`: 2D, 3D, improved 3D ve Thermal Fin eğitim
  metrikleri. Güncel 10-seed tablolar büyük ölçüde buradan besleniyor.
- `thermal_pinn/checkpoints/thermal_fin/`: Thermal Fin fixed-k/adaptive ve
  seed metrikleri.
- `thermal_pinn/results/thermal_fin/06_tables/`: Thermal Fin temiz CSV/JSON/MD
  çıktıları. Bu klasördeki tablo bazı yerlerde tekil/temiz görsel sonucu gibi
  davranıyor; 10-seed rapor tablolarıyla karıştırılmamalı.
- `thermal_pinn/results/fem_baseline/`: temporal interpolation/FEM baseline
  karşılaştırmaları.
- `thermal_pinn/reports/thesis_uia/`: tez `.tex` kaynakları ve rapor figür
  üretim betikleri.
- `thermal_pinn/scripts/aggregate_seeds.py`: 10-seed istatistiklerini üreten
  ana aggregation betiği.

Önemli not: `aggregate_seeds.py` içinde `--dim` argümanı tanımlı fakat filtrede
kullanılmıyor. Bu yüzden `--domain lshape --dim 3` çalıştırıldığında hem 2D
hem 3D `lshape` satırları aynı isimle basılıyor. Bu durum doğrudan tablo
üretimini bozmasa bile denetim ve rapor üretiminde karışıklık riski yaratıyor.

## 2. En Kritik Sayısal Tutarsızlıklar

### 2.1 3D Rectangular Prism L2 Yorumu Eski veya Yanlış

`results_3d.tex` satır 148--157 içinde Rectangular Prism için şu yorumlar
tabloyla uyuşmuyor:

- Bayesian/TPE için `$L_2 = 0.033$--$0.038$` denmiş; tablodaki mean değerler
  yaklaşık `0.036--0.037`.
- NSGA-II için `$k=5$` değerinde `0.071` ve MAE eşiğinin aşılması söylenmiş;
  tablodaki mean L2 `0.052`, MAE mean ise `13.42`, yani `15 C` eşiğinin altında.
- Bayesian/TPE seed variance `sigma <= 0.014` denmiş; tablodaki mean satırında
  en yüksek std `0.008`.
- NSGA-II `k=5` std `0.017` denmiş; tablodaki std `0.021`.

Öneri: Bu paragraf doğrudan `tab:l2_rectangular_3d` ve
`tab:cons_rectangular_3d` mean satırlarına göre yeniden yazılmalı.

### 2.2 3D Stacked Cubes L2 Eşik Yorumu Hassas Değil

`results_3d.tex` satır 390 sonrası Stacked Cubes için NSGA-II ve NSGA-III'ün
`k=4--5` aralığında kabul edilebilir bölgeye ulaştığı söyleniyor. Ancak tabloya
göre:

- NSGA-II `k=4 = 0.059`, `k=5 = 0.069`; caption tanımına göre bunlar hâlâ
  `<0.07` ve "excellent".
- NSGA-III `k=5 = 0.074`; sadece bu değer `0.07--0.09` kabul edilebilir
  bandına giriyor.

Öneri: "both architectures reach the acceptable zone" yerine "NSGA-II remains
just inside the excellent band, while NSGA-III crosses into the acceptable band
at k=5" benzeri bir ifade kullanılmalı.

### 2.3 3D L-shape L2 ve MAE Yorumu Ciddi Şekilde Yanlış

`results_3d.tex` satır 503--512 içindeki L-shape paragrafında birkaç kritik
hata var:

- Bayesian/TPE `$L_2 = 0.033$--$0.040$` denmiş; tablodaki mean değerler
  `0.042--0.050`.
- NSGA-II `k=5` için `$L_2=0.094`, `sigma=0.025` denmiş; tablodaki mean satırı
  `0.053 ± 0.030`.
- "mean MAE exceeding 27 C" ifadesi mean değil, Seed A değerine yakın görünüyor.
  Tablodaki NSGA-II `k=5` mean MAE `15.65 C`.
- "NSGA-III and Bayesian/TPE remain within acceptable range" ifadesi zayıf;
  ikisi de `<0.07` olduğu için L2 açısından "excellent" aralığında.

Öneri: Bu paragraf tamamen güncellenmeli. Burada en önemli doğru sonuç:
NSGA-II/III L-shape'te düşük k değerlerinde L2 bakımından Bayesian/TPE'den iyi,
ama NSGA-II `k=5` MAE tarafında yüksek varyansla eşiği aşıyor.

### 2.4 3D Best-k Şekil Caption'ları Tabloyla Uyuşmuyor

`results_3d.tex` satır 518--523 şeklin "lowest mean MAE" için seçildiğini
söylüyor. Fakat alt caption'larda:

- Bayesian L-shape `k=3` yazıyor; tabloya göre Bayesian L-shape en düşük mean
  MAE `k=1` (`10.20 C`).
- NSGA-II L-shape `k=3` yazıyor; tabloya göre NSGA-II L-shape en düşük mean
  MAE `k=1` (`4.54 C`).

Öneri: Ya görseller gerçekten `k=3` için seçildiyse "lowest-error skip factor"
iddiası değiştirilmeli, ya da L-shape görselleri/caption'ları `k=1` ile
uyumlu hâle getirilmeli.

### 2.5 Std Tanımı Kod ile Rapor Arasında Farklı

`aggregate_seeds.py` std hesabında `np.std(..., ddof=1)` kullanıyor; bu sample
std'dir. Rapor tablolarındaki bazı değerler ise population std (`ddof=0`) ile
uyumlu görünüyor. Örneğin 3D L-shape Bayesian `k=1` için aggregation çıktısı
`10.20 ± 1.48`, tablo ise `10.20 ± 1.40`.

Öneri: Ya raporda "population standard deviation" açıkça belirtilmeli ya da
tablo üretimi aggregation script ile aynı sample std hesabına çekilmeli.
Savunma için en temiz seçenek: tek bir std tanımı seçilip tüm tablolar aynı
betikten yeniden üretilmeli.

### 2.6 Conclusion ve Abstract'taki Seed-Variance İddiası Yanlış

`conclusion.tex` satır 117--120 ve `abstract.tex` satır 25--26 civarında,
standard deviation değerlerinin bütün domain ve mimarilerde `k <= 4` için
`0.9 C` altında kaldığı, `k=5` için de yaklaşık `±0.5 C` seviyesine genişlediği
söyleniyor. Bu ifade güncel tablolarla uyuşmuyor.

Örnekler:

- 3D Cylinder NSGA-II: `k=4` std `8.21 C`, `k=5` std `12.28 C`.
- 3D Cylinder NSGA-III: `k=4` std `7.21 C`.
- 3D Stacked Cubes NSGA-II: `k=3` std `4.97 C`, `k=4` std `4.59 C`.
- 3D L-shape NSGA-II: `k=5` std `8.85 C`.
- 2D Circle/L-shape compact mimarilerinde de `k<=4` için `0.9 C` üstünde std
  değerleri var.

Öneri: Bu iddia yalnızca Thermal Fin Bayesian/TPE veya belirli stabil alt grup
için geçerliyse kapsamı daraltılmalı. Aksi halde conclusion ve abstract,
"variance is low for Bayesian/TPE but can be large for compact NSGA models on
curved/interface/reentrant geometries" şeklinde düzeltilmeli.

### 2.7 Thermal Fin Kaynak Sürümü Netleştirilmeli

Tezdeki Thermal Fin 10-seed fixed-k tablosu Bayesian/TPE Fourier için `k=5`
değerini `12.55 ± 0.29 C` olarak veriyor. `aggregate_seeds.py` çıktısı da bunu
doğruluyor. Ancak `results/thermal_fin/06_tables/thermal_fin_clean_results.md`
içinde Bayesian/TPE fixed-k `k=5` satırı `15.19 C` görünüyor. Bu dosya muhtemelen
tekil/temiz görsel üretim sonucunu veya Fourier öncesi/başka sürümü temsil
ediyor.

Öneri: Raporun ana sayısal iddiası için hangi kaynak dosyanın kullanıldığı açık
olmalı. `thermal_fin_clean_results.md` figür üretiminde kullanılıyorsa,
caption veya dosya adı bu tablonun 10-seed consolidated tablo olmadığını
belirtmeli. Aksi halde okuyucu Bayesian/TPE'nin `k=5`te eşiği geçtiğini
sanabilir.

## 3. Metodoloji ve Kod Diliyle İlgili Eksiler

### 3.1 FEM/FD İsimlendirmesi Karışık

Metinde çok yerde "FEM" deniyor, ancak sonuç kaynaklarında ve method tablosunda
birçok referans "Own FD solver" olarak geçiyor. `conclusion.tex` içinde de
"thesis's own FD solver" ifadesi kullanılmış. Bu iki kavram aynı şey gibi
sunulursa jüri teknik olarak sorgulayabilir.

Öneri: Şu ayrım netleştirilmeli:

- Eğer gerçek yöntem structured-grid finite difference ise "FD reference solver"
  denmeli.
- Eğer tez terminolojisi endüstriyel bağlam nedeniyle FEM-anchored diyorsa,
  "FEM/FD reference anchor" veya "finite-element-style reference anchor" gibi
  ara bir ifade değil, açık ve teknik olarak doğru bir adlandırma kullanılmalı.
- "FEM solver calls" ana iddiası korunacaksa kodda kullanılan solver tipinin
  neden FEM yerine geçerli referans kabul edildiği açıklanmalı.

### 3.2 L-shape Domain Adı 2D/3D İçin Çakışıyor

Aggregation çıktısında 2D ve 3D `lshape` aynı domain adıyla görünüyor.
Bu, rapor tablosu üretiminde ve otomatik summary denetimlerinde riskli.

Öneri: İç veri modelinde `lshape_2d` ve `lshape_3d` gibi açık adlar
kullanılmalı veya en azından summary çıktısında `dim` kolonu basılmalı ve
`--dim` filtresi gerçekten uygulanmalı.

### 3.3 Eski İnceleme Raporu Güncel Değil

`Tez_Inceleme_Raporu.md` dosyası hâlâ "3-seed ortalamaları" gibi eski
ifadeler içeriyor. Güncel `.tex` kaynaklarında ana sonuçlar 10 seed olarak
raporlanmış. Bu eski inceleme dosyası savunma öncesi kontrol listesi olarak
kullanılacaksa güncellenmeli.

## 4. "We" mi, 3. Tekil/Edilgen Dil mi?

Tez genelinde "we" kalıbı baskın değil. Hızlı sayım:

- `we/We`: yaklaşık 15 kullanım.
- `our/Our`: 1 kullanım.
- `This thesis`, `the thesis`, `the framework`, `the study` gibi edilgen/3.
  tekil akademik kalıplar: yaklaşık 62 kullanım.

Yani metin genel olarak 3. tekil/nesnel akademik anlatıma daha yakın. "We" en
çok method ve conclusion bölümlerinde görülüyor:

- `method.tex`: "We swept...", "we used...", "We reserved..." gibi yöntem
  seçimlerini anlatan cümleler.
- `conclusion.tex`: "we built", "We found" gibi sonuç özetleri.
- `results_thermal_fin.tex`: bir yerde "before we go into the details".

Öneri: Eğer tez tek yazarlı ve daha resmi bir UiA master tezi tonu isteniyorsa
`we` cümleleri kolayca edilgen/nesnel dile çevrilebilir:

- "We swept k=1,...,5" -> "The skip factor was swept over k=1,...,5"
- "we used" -> "the experiments used"
- "We found that" -> "The results show that"

Ancak mevcut kullanım çok yoğun değil; savunma için kritik hata değil, stil
tutarlılığı konusu.

## 5. Öncelikli Düzeltme Planı

1. `results_3d.tex` içindeki Rectangular, Stacked Cubes ve L-shape L2 yorumları
   tablo mean/std değerleriyle yeniden yazılmalı.
2. `fig:3d_bestk_fields` için L-shape `k` caption'ları ve görsel seçim mantığı
   kontrol edilmeli.
3. `abstract.tex` ve `conclusion.tex` içindeki seed-variance iddiası daraltılmalı
   veya güncel büyük std değerleriyle uyumlu hâle getirilmeli.
4. Thermal Fin için `thermal_fin_clean_results.md` ile 10-seed consolidated
   tablo arasındaki fark açıklanmalı; raporda hangi kaynağın ana sonuç olduğu
   netleştirilmeli.
5. Std hesabı için karar verilmeli: sample std mi population std mi? Tüm
   tablolar aynı tanıma göre güncellenmeli.
6. `aggregate_seeds.py` içinde `--dim` filtresi uygulanmalı ve summary çıktısına
   `dim` kolonu eklenmeli.
7. FEM/FD terminolojisi method, conclusion ve figure caption'larında tek
   teknik çizgiye çekilmeli.
8. Mevcut `Tez_Inceleme_Raporu.md`, 10-seed güncel tez kaynaklarına göre
   revize edilmeli.
9. İstenirse "we" içeren cümleler edilgen akademik dile dönüştürülmeli; bu
   düşük öncelikli bir stil temizliği.

## 6. Kısa Savunma Öncesi Özet

Tezin ana deney matrisi güçlü ve 10-seed raporlama iyi bir artı. Bu taslakta
`quenching_mswp` hiçbir sonuç iddiasına dahil edilmemiştir. En büyük risk,
mevcut tez tabloları ile 3D sonuç yorum paragraflarının aynı sürümde olmaması.
Özellikle 3D Rectangular ve 3D L-shape L2 yorumları jüri tarafından tabloyla
karşılaştırılırsa hemen fark edilecek türden sayısal uyumsuzluklar içeriyor.
İkinci büyük risk abstract/conclusion tarafındaki "std her yerde düşük" iddiası;
3D ve bazı 2D compact mimari tabloları bu iddiayı desteklemiyor. Bu noktalar
düzeltilirse raporun güvenilirliği belirgin şekilde artar.
