# FEM h(T) Training — Tüm Sonuçlar

Bu oturumda yapılanların özeti. Tüm deney parametreleri ve sonuçlar.

---

## Fizik

- **Malzeme:** A356 alüminyum, k=150 W/(m·K), ρcₚ=2.4×10⁶ J/(m³·K)
- **Başlangıç sıcaklığı:** T₀ = 540°C
- **Su sıcaklığı:** T_w = 20°C
- **h(T) boiling curve:** 5 rejimli parçalı doğrusal (film boiling h=700 → nucleate peak h=20000 → single-phase h=2500)

## FEM Referans Verisi

Dosyalar: `thermal_pinn/data/`

| Dosya | Düğüm sayısı | t aralığı | t=30s Tmin |
|-------|-------------|-----------|-----------|
| `fem_hT_rectangle.npz` | 1976 | 0–30s, Δt=1.5s (21 snapshot) | 324.6°C |
| `fem_hT_circle.npz` | 3317 | 0–30s, Δt=1.5s (21 snapshot) | 426.4°C |
| `fem_hT_lshape.npz` | 1119 | 0–30s, Δt=1.5s (21 snapshot) | 324.5°C |

FEM parametreleri: dt_iç=0.5s, implicit Euler, Robin BC h(T), T∈[T_w, T₀] clip.

---

## Model

**NAS-PINN Bayesian/TPE** — 5 gizli katman × 151 nöron, ReLU aktivasyon  
IC-consistent residual formülasyonu: θ(τ=0) = θ_ic her noktada tam sağlanır.  
Normalleştirme: x_norm = x/Lx, y_norm = y/Ly (lo=0 sabit).

---

## Eğitim Parametreleri (tüm deneylerde)

| Parametre | Değer |
|-----------|-------|
| n_domain | 1500 |
| n_bc | 300 |
| n_epochs (Adam) | 800 |
| L-BFGS iters | 50 |
| lr | 1e-3 → 1e-5 (cosine) |
| end supervision weight | 10.0 |
| GPU | NVIDIA Tesla V100-SXM3 32GB |

---

## Sonuçlar — Fixed k Sweep (k=1..5)

### Rectangle (1.3×0.6 m)

| k | Mean MAE (°C) | Mean L2 | Windows | FEM saved |
|---|--------------|---------|---------|-----------|
| **1** ★ | **5.68** | — | 20 | 0% |
| 2 | 5.93 | — | 10 | 50% |
| 3 | ~6.x | — | 7 | 65% |
| 4 | ~7.x | — | 5 | 75% |
| 5 | ~8.x | — | 4 | 80% |

Checkpoint: `rectangle_bayesian_fem_hT_k{1..5}_dim2.pt`

### Circle (R=0.3 m, merkez orijin)

| k | Mean MAE (°C) | Windows | FEM saved |
|---|--------------|---------|-----------|
| 1 | 6.01 | 20 | 0% |
| 2 | 7.32 | 10 | 50% |
| 3 | ~7.x | 7 | 65% |
| **4** ★ | **7.77** | 5 | **75%** |
| 5 | 8.09 | 4 | 80% |

Checkpoint: `circle_bayesian_fem_hT_k{1..5}_dim2.pt`

### L-shape (2×2 m, sağ üst çeyrek eksik)

| k | Mean MAE (°C) | Windows | FEM saved |
|---|--------------|---------|-----------|
| 1 | 4.96 | 20 | 0% |
| 2 | 4.01 | 10 | 50% |
| 3 | 4.49 | 7 | 65% |
| 4 | 4.32 | 5 | 75% |
| **5** ★ | **4.19** | 4 | **80%** |

Checkpoint: `lshape_bayesian_fem_hT_k{1..5}_dim2.pt`

---

## Sonuçlar — Adaptive-k (k_init=1, thresh_up=2°C, thresh_down=5°C)

| Domain | Mean MAE (°C) | Windows | FEM saved | k schedule (ilk 10) |
|--------|--------------|---------|-----------|---------------------|
| rectangle | 6.61 | 18 | 10% | [1,2,2,1,1,1,1,1,1,1,...] |
| circle | 5.29 | 17 | 15% | [1,2,2,2,1,1,1,1,1,1,...] |
| lshape | 5.43 | 15 | 25% | [1,2,2,2,2,2,1,1,1,1,...] |

Checkpoint: `{domain}_bayesian_adaptive_fem_hT_dim2.pt`

**Not:** thresh_up=2°C h(T) rejimi için çok katı — model quasi-steady fazda da k=1'de kalıyor.

---

## Sonuçlar — PINN-only (FEM anchor yok, IC zinciri)

| Domain | Mean MAE (°C) | Açıklama |
|--------|--------------|---------|
| rectangle | 51.0 | ❌ Hata monoton birikiyor (pencere 1: 20.7°C → pencere 20: 76.8°C) |
| circle | 23.6 | ❌ Pencere 4'te ani sıçrama (31°C) |
| lshape | 68.9 | ❌ Son pencereler 110°C+ hata |

Checkpoint: `{domain}_bayesian_pinn_only_fem_hT_k1_dim2.pt`

**Sonuç:** FEM anchoring her pencerede zorunlu. Sadece t=0 IC verilerek PINN zincirlenmesi 5-15× hata artışına yol açıyor.

---

## Temel Dosyalar

```
thermal_pinn/
├── data/
│   ├── fem_hT_rectangle.npz
│   ├── fem_hT_circle.npz
│   └── fem_hT_lshape.npz
├── physics/
│   ├── fem/
│   │   ├── base_solver.py          # FEniCS implicit Euler solver
│   │   ├── boiling_curve.py        # h(T) 5-rejim eğrisi
│   │   ├── domains.py              # Rectangle/Circle/LShape mesh builder
│   │   ├── fem_reference.py        # FEMReference (.npz interpolator)
│   │   ├── generate_fem_data.py    # .npz üretici (dolfin gerekli)
│   │   ├── run_all_domains_compare.py  # 3×3 görsel
│   │   ├── plot_strategy_comparison.py # 3 strateji karşılaştırma
│   │   └── make_results_table.py   # Tam sonuç tablosu
│   └── fem_reference.py            # make_reference_domain() factory
├── training/
│   ├── train_all.py                # Fixed-k sweep
│   ├── train_adaptive_k.py         # Adaptive-k (--tag, --k_init eklendi)
│   └── train_pinn_only.py          # PINN-only zinciri (YENİ)
└── checkpoints/
    ├── {domain}_bayesian_fem_hT_k{1..5}_dim2.pt    # 15 model
    ├── {domain}_bayesian_adaptive_fem_hT_dim2.pt   # 3 model
    ├── {domain}_bayesian_pinn_only_fem_hT_k1_dim2.pt  # 3 model
    └── *_metrics.json                               # tüm metrikler
```

---

## Koordinat Sistemi (ÖNEMLİ)

| Domain | Fiziksel aralık | PINN girişi |
|--------|----------------|-------------|
| rectangle | x∈[0,1.3], y∈[0,0.6] | x/1.3, y/0.6 → [0,1] |
| circle | x∈[-0.3,0.3], y∈[-0.3,0.3] | x/0.6, y/0.6 → [-0.5,0.5] |
| lshape | x∈[0,2], y∈[0,2] | x/2, y/2 → [0,1] |

Normalleştirme: `x_norm = x / Lx` (lo=0 sabit, x_min çıkarılmaz).

---

*Oluşturulma: Haziran 2026 — NAS-PINNS1 sunucusu*
