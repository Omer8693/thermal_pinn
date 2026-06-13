# Tez İnceleme Raporu

**Tez:** Neural Architecture Search Guided Physics Informed Neural Networks for Finite Element Method Anchored Transient Heat Transfer Simulation
**Yazar:** Ömer Çetinkaya
**Danışman:** Prof. Turgay Çelik
**Kurum:** University of Agder, 2026
**Sayfa Sayısı:** 103

---

## 1. GENEL DEĞERLENDİRME

Tez, mühendislik açısından anlamlı ve özgün bir soruya cevap arıyor: "FEM çözücüsü çağrılarının ne kadarı, endüstriyel tolerans dahilinde, PINN tahminleriyle değiştirilebilir?" Multi-Step Window Prediction (MSWP) çerçevesi, 9 farklı geometri üzerinde, 3 farklı NAS stratejisi ile sistematik olarak değerlendirilmiş. Bu uygulamalı, mühendislik odaklı yaklaşım tezin en güçlü yönü.

**Genel kalite:** Yüksek. Metodoloji ve sonuçlar bölümleri profesyonel. Ancak son okuma/tashih (proofreading) aşaması eksik bırakılmış: birkaç kritik LaTeX hatası ve sayısal tutarsızlık savunma öncesi mutlaka düzeltilmeli.

---

## 2. ARTILAR (GÜÇLÜ YÖNLER)

### 2.1 Bilimsel ve Metodolojik Güç
- **Net araştırma sorusu:** "En düşük hata değil, en yüksek kabul edilebilir k" şeklindeki problem formülasyonu çok net. Bu, mühendislik motivasyonuyla iyi örtüşüyor.
- **Geniş deneysel matris:** 9 alan (3 adet 2D, 4 adet 3D, subframe, Thermal Fin) × 3 mimari × 5 skip faktörü + adaptif mod + PINN-only mod = kapsamlı bir değerlendirme matrisi.
- **3 NAS stratejisi karşılaştırması:** Bayesian/TPE, NSGA-II, NSGA-III karşılaştırması transient PINN literatüründe pratik rehber niteliğinde.
- **Negatif sonuçların açıkça raporlanması:** PINN-only modun başarısızlığının (Tablo 4.24, 4.25) saklanmadan, hatta vurgulanarak raporlanması metodolojik dürüstlük açısından çok değerli.
- **Üretim kabul eşiği (acceptance threshold):** 15 °C Thermal Fin için, 10 °C subframe için, 520 °C aralığın %2-3'ü olarak fiziksel motivasyonla bağlanmış.
- **Çoklu seed (3 tohum) ortalamaları:** Sonuçların yeniden üretilebilirliği için seed A/B/C ortalamaları raporlanmış. (Ama "Limitations" bölümünde çelişki var — aşağı bakınız.)
- **Ablation çalışmaları (Appendix I):** Fourier feature ve endpoint supervision ablation'ları, mimari seçimlerin etkisini niceliksel olarak ortaya koymuş.

### 2.2 Yazım Stili
- Genelde akıcı ve okunabilir bir İngilizce. "We did/we found" yaklaşımı, akademik standartlara uygun ve okuyucu dostu.
- Sonuçlar ile tartışma arasında net bir ayrım var.
- Tablolar zengin (ham seed verisi + ortalama ± std verilmiş — istatistiksel şeffaflık).

### 2.3 Pratik/Endüstriyel Bağlantı
- Mortensen et al. [1] referansı ile endüstriyel alüminyum dökme subframe sorununa açık bağlantı.
- Tablo 5.1'deki break-even analizi (kaç simülasyon koşumundan sonra eğitim maliyetinin amorti edileceği) pratik karar verme için kullanışlı.

---

#
 

### 3.3 Sunum Sorunları
- **İlk birkaç paragraf:** Giriş bölümünde "It sounds simple but..." gibi konuşma dili akademik teze fazla samimi geliyor.
- **Bölüm 5 (Discussion):** Sonuç bölümüyle (Bölüm 6.1) önemli ölçüde örtüşüyor — daha açık ayrım gerekli.

---

## 4. KRİTİK HATALAR (MUTLAKA DÜZELTİLMELİ)

### 4.1 LaTeX Çapraz-Referans (Cross-Reference) Hataları — KRİTİK

| # | Konum | Sorun |
|---|-------|-------|
| **4.1.1** | Sayfa 15, **Figure 3.1** caption sonu | LaTeX yer tutucu metin görünüyor: *"**Note: place NAS-PINN Architecture Search and Window-Based Training.png in Figures/.**"* Bu, yazardan kendine bırakılmış geliştirici notu, savunma versiyonunda kalmamalı. Şekil dosyası zaten yerleştirilmiş, sadece bu cümle silinmeli. |
| **4.1.2** | Sayfa 42, **Section 4.3.1** (Subframe Hybrid Results), 2 yerde | Metinde "**Table ??**" yazıyor: *"Table ?? shows the mean window MAE..."* ve *"The L2 relative error in Table ??..."*. Bunlar bozuk LaTeX referansları (`\ref{}` tanımsız). Hedef tabloların bibtex/label'ları kontrol edilip gerçek tablo numaraları gelmeli. |
| **4.1.3** | Sayfa 70, **Appendix C** giriş paragrafı | "**Figure ??** shows the MSWP strategy used throughout this thesis." Şekil C.1'i referans etmeli. |

### 4.2 Sayısal Tutarsızlıklar — KRİTİK

| # | Yer 1 | Yer 2 | Sorun |
|---|-------|-------|-------|
| **4.2.1** | Bölüm 3.3.1: *"We ran **50 trials**"* (Bayesian/TPE) | Appendix E: *"...ran for **150 trials**"* | Trial sayısı çelişiyor. Hangisi doğru? |
| **4.2.2** | Bölüm 3.3.1: NSGA-II/III için *"**15 generations**"* | Appendix E: *"...ran for **30 generations**"* | Generation sayısı çelişiyor. |
| **4.2.3** | Bölüm 3.3.1: NSGA-III için *"population of **24**"* | Appendix E: *"population of **20**"* | Popülasyon büyüklüğü çelişiyor. |
| **4.2.4** | Bölüm 2.4.1: Layers *"{2, 3, 4, 5}"*, activations *"{ReLU, tanh, sigmoid}"* | Appendix E Tablo E.1: Layers *"2-6"*, activations *"{ReLU, tanh, SiLU, GELU}"* | NAS arama uzayı tarifleri **tamamen farklı**. Sigmoid vs. SiLU+GELU karışıklığı olabilir. |
| **4.2.5** | Tablo 3.5 başlığı: *"NVIDIA **V100**"* | Tablo 3.5 hemen altındaki metin (sayfa 19): *"NVIDIA **RTX 3060** GPU"*. Ayrıca Appendix A Tablo A.1: *"NVIDIA RTX 3060"*. Sonra Bölüm 5.4 (sayfa 61): *"on an NVIDIA **V100** GPU"* | GPU donanımı çelişkili (V100 ≫ RTX 3060). Eğitim hangi donanımda yapıldı? Bu, raporlanan wall-clock zamanlarını etkiler. |
| **4.2.6** | Tezin her yerinde 3-seed (A/B/C) ortalama ± std raporlanıyor | Bölüm 6.2 Limitations madde 5: *"**Each (domain, architecture, k) combination was executed once**. Seed sensitivity was not systematically quantified..."* | **Çelişki:** Tüm tablolar üç tohum verilerini gösteriyor ama "Limitations" tek seed çalıştırıldı diyor. Limitations bölümü güncellenmeli. |

### 4.3 Tablolar Listesi (List of Tables) — ÖNEMLİ
- List of Tables'ta **Tablo 4.17 ve 4.18 yok** — 4.16'dan doğrudan 4.19'a atlanmış (Subframe surrogate sonuçlar tabloları). Bu, "Table ??" referans hatasıyla muhtemelen aynı kaynaktan; eksik tablolar oluşturulmamış veya etiketleri kayıp. Bölüm 4.3.1'de bahsedilen MAE ve L2 tabloları bunlar olabilir.

### 4.4 Beyan Sayfası (Obligatorisk gruppeerklæring) — RESMİ
- 2. sayfada Norveç dilinde zorunlu beyan formu var. Her madde için "Ja / Nei" (Evet/Hayır) seçenekleri yer alıyor. **Hiçbiri işaretlenmemiş**. Üniversite yönetmeliğine göre bu form imzalanıp/işaretlenip teslim edilmeli. Tezin resmi kabulü için bu sayfa muhtemelen güncellenmeli.

---

## 5. KÜÇÜK YAZIM/EDİTÖRİYAL HATALAR

### 5.1 Tekrarlanan kelime
- **Sayfa 23** (Bölüm 3.4.6, son paragraf): *"...we therefore used the **subframe surrogate surrogate** to test..."* — "surrogate" iki kez yazılmış. Birini silin.

### 5.2 Tutarsız terminoloji
- "Subframe surrogate" vs. "Subframe-like" vs. "subframe-like surrogate" — Tezde tüm üç form da kullanılmış. Tek bir form benimsenmeli (önerim: **subframe surrogate**).
- "Plain MLP" vs. "Plain IC-consistent MLP" — bazen kısa, bazen uzun form. Tutarlılık iyi olur.

### 5.3 Kapak/Başlık Sayfası
- **Yazar adı:** "ÖMER CETINKAYA" — Türkçe "Çetinkaya" yazımıyla "Ö" var ama "Ç" yok. Eğer "Ö" tutulacaksa "ÖMER ÇETİNKAYA" daha tutarlı; uluslararası yazımı tercih edilirse "OMER CETINKAYA". Şu anki karışık form ("Ö" var, "Ç" yok) tutarsız.
- **Faculty/Department:** "Faculty of Engineering and Science" (Science tekil) ve "Department of Engineering and Sciences" (Sciences çoğul). UiA'nın resmi adı kontrol edilmeli. UiA'nın gerçek adı "Faculty of Engineering and Science"tır (her ikisi de tekil); "Department of Engineering Sciences" olabilir. Resmi UiA sayfasından kontrol edilmesi öneriliyor.

### 5.4 Cümle düzeyi
- **Sayfa 60, Bölüm 5.3:** *"**This does not imply this means** PINN-only operation is impossible..."* — "does not imply" ve "this means" gereksiz çift olumsuz/yedek ifade. Şöyle değiştirilebilir: *"This does not imply PINN-only operation is impossible..."*
- **Sayfa 1, Bölüm 1 sonu:** *"...for the FEM-anchored hybrid (where FEM provides the IC at each anchor) and the PINN-only rollout (where FEM is used only at t = 0)."* — açıklayıcı ama biraz uzun, kısaltılabilir.
- **Sayfa 31, Bölüm 4.1.4:** *"Full numerical values are provided in the seed sensitivity tables in Section 4.1.4."* — Bölüm 4.1.4'ün içinde olduğunuz bölüme atıf yapıyorsunuz. Bu kendi kendine referans hatalı; muhtemelen başka bir bölüme atıf olmalı veya sadece "above" / "below" kullanılmalı.
- **Sayfa 42 son cümle, Bölüm 4.3.1 başında**: Subframe surrogate sayfasında ön bilgi yetersiz; Figure 4.8 sayfa 42'de geliyor ama domain Section 3.4.6'da hiç görsel olarak gösterilmemişti.

### 5.5 Şekil/Tablo başlık (caption) sorunları
- **Figure D.1 caption:** *"Filled bars: warm-start (weights carried from the previous window); open bars: cold-start (random re-initialisation each window)."* — Ama görsel lejantta üç seri var: "Cold-Start vs v2 (Fourier+SA) vs Warm-Start (500 ep)". Üçüncü seri (v2) caption'da açıklanmamış. Aynı durum Figure D.2 için de geçerli.
- **Tablo 4.1 ve Tablo 4.8:** Bölüm 3.4.3 Tablo 3.7'de aynı parametreleri zaten verdiniz. Tekrar gereksiz olabilir veya Tablo 4.1/4.8 sadece "training parameters" üzerine odaklanmalı (fiziksel parametreler Tablo 3.7'ye referansla).

### 5.6 Notasyon
- Tezde **kT** (Vol. heat capacity altında **k subscript T**) — bazı yerde "thermal conductivity" sembolü olarak kullanılmış, ama Tablo 4.1 ve 4.8'de aynı kavram **λ** olarak yazılmış. Tek bir sembol tercih edilmeli (önerim: λ).

### 5.7 Çift "**only**" hatası, sayfa 65 Future Work
- *"...the same MSWP pipeline can be applied to **the real mesh once those data are converted** into the required format."* — Burada gramer açısından "those data are converted" yerine "that data is converted" veya "the data are converted" daha doğal. (İngilizcede "data" hem tekil hem çoğul kabul edilir ama "those data" eski kullanım.)

### 5.8 Bibliografi
- **Referans [1] Mortensen et al. 2026:** Şu an Mayıs 2026; bu makalenin DOI'sinin geçerli olup olmadığı doğrulanmalı (doi: 10.1007/s00170-026-17515-w). 2026 yayını olarak görünüyor; tezin teslim tarihinde mevcut olduğundan emin olun.
- **Referans [9] Zhao et al. 2025:** 2025 tarihli; OK.
- Referanslar genel olarak doğru biçimde verilmiş, ancak [16] ve [17] gibi NeurIPS bildirileri için DOI yerine sadece URL var — IEEE/elsevier stilinde DOI'ler tercih edilir (zorunlu değil).

### 5.9 Mizanpaj
- Tablolarda bazı yerlerde sembol kutu olarak görünüyor (yeşil, koyu mavi vs. işaretler). Örneğin Tablo 4.2'deki: *"= lowest mean per skip factor; = within 10 °C engineering threshold."* — Burada "=" işaretinden önce muhtemelen renkli/sembol gelmesi gerekiyor ama PDF'de boş görünüyor. Renkli işaretlerin (✓, ★, vs.) gerçekten basıldığından emin olun.

---

## 6. YAPILMASI GEREKEN DÜZELTMELER — ÖNCELİK SIRASI

### Öncelik 1 (Savunma Öncesi MUTLAKA)
1. ✅ **Şekil 3.1 caption'ından** "Note: place NAS-PINN Architecture..." geliştirici notunu silin.
2. ✅ **Sayfa 42'deki iki "Table ??"** referansını gerçek tablo numaralarıyla değiştirin.
3. ✅ **Sayfa 70 Appendix C'deki "Figure ??"** referansını **Figure C.1** olarak düzeltin.
4. ✅ **NAS arama uzayı tutarsızlıklarını** giderin (50/150 trials, 15/30 generations, 20/24 population, sigmoid/SiLU+GELU, 2-5/2-6 layers). Bölüm 2.4.1, Bölüm 3.3.1 ve Appendix E.1 aynı sayıları söylemeli.
5. ✅ **GPU tutarsızlığını** giderin: V100 mi yoksa RTX 3060 mı? Tüm yerleri (Tablo 3.5 başlığı + altındaki paragraf, Tablo A.1, Bölüm 5.4) aynı bilgiyi vermeli.
6. ✅ **Limitations madde 5'i güncelleyin:** Tek seed çalıştırıldı iddiası yanlış, 3-seed ortalamalar raporlanmış.
7. ✅ **Tablo 4.17 ve 4.18'in** List of Tables'a girmemesi: bu tabloları yaratın veya numaralandırmayı yeniden yapın.
8. ✅ **Norveç beyan formunu** işaretleyin.

### Öncelik 2 (Kalite için)
9. ✅ "subframe surrogate surrogate" çift sözcüğü silin (sayfa 23).
10. ✅ Kapak sayfasında yazar adının tutarlı yazımı.
11. ✅ "Subframe-like" vs "subframe surrogate" tutarlı kullanımı.
12. ✅ Figure D.1/D.2 caption'larında üçüncü serinin (v2 Fourier+SA) açıklaması.
13. ✅ kT/λ sembollerinin tutarlı kullanımı.
14. ✅ Tablolardaki renkli/sembol işaretlerinin gerçekten basıldığından emin olun.

### Öncelik 3 (Stil)
15. ✅ Bölüm 5 (Discussion) ile Bölüm 6.1 (Conclusion) arasındaki örtüşmeyi azaltın.
16. ✅ Giriş bölümünde konuşma dilini biraz akademikleştirin.
17. ✅ "This does not imply this means" gibi yedek ifadeleri temizleyin.

---

## 7. ÖZET

**Tezin akademik içeriği güçlü, ancak son okuma eksik.** Yukarıdaki Öncelik 1 listesindeki 8 madde mutlaka düzeltilmeli — bunlar savunma jürisi tarafından hemen fark edilecek türden hatalar ve tezin profesyonelliğini olumsuz etkiler. Özellikle:

- **3 LaTeX broken reference** (Figure 3.1 dev notu, Table ?? × 2, Figure ?? × 1) — bunlar göze çarpan teknik hatalar.
- **NAS parametre çelişkileri** ve **GPU çelişkisi** — bunlar yazarın kendi çalışmasını yeterince kontrol etmediği izlenimi verir.
- **3-seed vs. tek seed çelişkisi** — bu en kafa karıştırıcı çelişki, çünkü Limitations bölümü tezin ana iddialarını çürütüyor gibi görünüyor.

Bu düzeltmeler yapıldığında, tez yüksek kaliteli bir master tezi standardındadır.

---
*Bu rapor, IKT590_Thesis.pdf'in 103 sayfalık tam metni okunarak hazırlanmıştır.*
