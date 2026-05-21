# Benzer Görsel ve Metin Bulucu

Fotoğraflardaki tekrar eden benzer metinleri ve görselleri otomatik olarak tespit eden, gruplandıran ve temizleyen bir web uygulaması. Klasör yolu girerek ya da dosyaları doğrudan yükleyerek aynı veya çok benzer fotoğrafları bulabilir, fazlalarını silerek koleksiyon temizliği yapabilirsiniz.

---

## Ne Yapar?

- Fotoğraflardaki metni **OCR** ile okur (Türkçe + İngilizce)
- Metin içermeyen görsel, şema ve grafikleri **dHash** (görsel parmak izi) ile karşılaştırır
- Her iki yöntemi birleştiren **hibrit mod** sayesinde hem yazılı sorular hem de görseller için yüksek doğruluk sağlar
- Birbirine benzeyen dosyaları **gruplara** ayırır, en yüksek çözünürlüklüyü otomatik işaretler
- Tekrar eden dosyaları **tek tıkla diskten silebilir**
- Sonuçları **JSON** veya **TXT** rapor olarak indirir
- Gerçek zamanlı ilerleme çubuğu ile her dosyanın işlenişini takip eder
- NVIDIA GPU varsa analizi GPU ile **çok daha hızlı** tamamlar

### Desteklenen Dosya Formatları

`.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff`

---

## Gereksinimler

| Gereksinim | Notlar |
|---|---|
| **Python 3.10+** | Zorunlu |
| **GPU (isteğe bağlı)** | NVIDIA + CUDA 12.x — olmasa da çalışır, sadece daha yavaş |

---

## Kurulum

### Windows — Tek Tıkla Başlat (Önerilen)

1. Bu repoyu [ZIP olarak indirin](../../archive/refs/heads/main.zip) ve bir klasöre çıkarın  
   *veya* terminalde şunu çalıştırın:
   ```
   git clone https://github.com/KULLANICI_ADI/soru-tekrar-bulucu.git
   cd soru-tekrar-bulucu
   ```
2. `baslat.bat` dosyasına **çift tıklayın**

`baslat.bat` şunları otomatik yapar:
- Sanal ortam (`venv`) oluşturur
- Bağımlılıkları yükler
- Sunucuyu başlatır
- Tarayıcıda `http://localhost:8000` adresini açar

> **Not:** `baslat.bat` PyTorch'u yüklemez. Eğer GPU hızlandırması istiyorsanız aşağıdaki "Manuel Kurulum" adımlarını izleyin.

---

### Manuel Kurulum (Tüm Platformlar)

#### Adım 1 — Python'u Kurun

Python'un kurulu olup olmadığını kontrol edin:

```bash
python --version
```

`Python 3.10` veya üstü bir sürüm çıkmalı. Kurulu değilse [python.org](https://www.python.org/downloads/) adresinden indirin.

> **Windows kullanıcıları:** Kurulum sırasında **"Add Python to PATH"** kutusunu işaretleyin.

#### Adım 2 — Repoyu İndirin

```bash
git clone https://github.com/KULLANICI_ADI/soru-tekrar-bulucu.git
cd soru-tekrar-bulucu
```

Git yoksa sayfanın sağ üstündeki **Code → Download ZIP** ile de indirebilirsiniz.

#### Adım 3 — Sanal Ortam Oluşturun

```bash
python -m venv venv
```

Sanal ortamı etkinleştirin:

- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

> Etkinleştirme başarılıysa terminal satırının başında `(venv)` görünür.

#### Adım 4 — PyTorch'u Kurun

`requirements.txt` çalıştırmadan önce PyTorch'u ayrıca kurmanız gerekir.

**GPU kullanacaksanız (NVIDIA CUDA 12.x):**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

> Hangi CUDA sürümünüzün olduğunu öğrenmek için terminalde `nvidia-smi` komutunu çalıştırın.  
> Farklı bir sürümünüz varsa `cu128` yerine `cu118`, `cu121` gibi ilgili etiketi yazın.

**Sadece CPU kullanacaksanız:**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

> GPU'nuz yoksa bu adımı tamamen atlayabilirsiniz; uygulama yine de çalışır.

#### Adım 5 — Kalan Bağımlılıkları Kurun

```bash
pip install -r requirements.txt
```

> **İlk kurulumda EasyOCR dil modellerini indirir (~400 MB).** Bu işlem yalnızca bir kez gerçekleşir; modeller `~/.EasyOCR/` klasörüne kaydedilir.

#### Adım 6 — Sunucuyu Başlatın

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Ardından tarayıcınızda şu adresi açın:

```
http://localhost:8000
```

---

## Kullanım

### 1. Kaynak Seçimi

| Mod | Ne Zaman Kullanılır |
|---|---|
| **Klasörden Aç** | Fotoğraflar diskte bir klasördeyse. Klasörün tam yolunu yapıştırın (Windows'ta Explorer adres çubuğundan `Ctrl+C` ile kopyalayabilirsiniz). Görsel önizleme ve silme işlemleri bu modda aktiftir. |
| **Dosya Seç** | Tek tek dosya seçmek ya da sürükle-bırak yapmak istiyorsanız. Bu modda silme işlemi yapılamaz; geçici kopyalar analiz sonrası otomatik silinir. |

### 2. Analiz Modu Seçimi

| Mod | Nasıl Çalışır | Ne Zaman Kullanılır |
|---|---|---|
| **Hibrit** *(varsayılan)* | Metin + görsel benzerliği birlikte değerlendirir | Hem yazılı sorular hem de görseller için en iyi sonuç |
| **Sadece Metin** | Yalnızca OCR ile okunan metni karşılaştırır | İçerik tamamen metinden oluşuyorsa |
| **Sadece Görsel** | Yalnızca dHash görsel parmak izini karşılaştırır | Metin olmayan görseller veya şemalar için |

### 3. Diğer Ayarlar

- **Dil** — Belgeler Türkçe ise `TR + EN` önerilir.
- **İşlemci** — `Otomatik` seçeneği GPU varsa GPU'yu, yoksa CPU'yu kullanır. `GPU` veya `CPU` ile manuel seçim de yapılabilir.

### 4. Analiz ve Sonuçlar

1. Kaynağı seçin, ayarları düzenleyin, **Analiz Et**'e tıklayın.
2. İlerleme çubuğu her dosyanın işlenişini gerçek zamanlı gösterir.
3. Analiz tamamlanınca iki bölüm görünür:
   - **Tekrar Eden Metinler ve Görseller** — Birbirine benzeyen dosya grupları. Her grupta en yüksek çözünürlüklü dosya **★ Korunacak** olarak işaretlenir, diğerleri **Silinecek** olarak gösterilir.
   - **Benzersiz Metinler ve Görseller** — Hiçbir başka dosyayla eşleşmeyen bağımsız dosyalar.
4. Bir gruptaki tekrar edenleri silmek için **Sil** butonunu, hepsini bir anda temizlemek için **Tüm Tekrarları Sil** butonunu kullanın.
5. Sonuçları **JSON** veya **TXT** formatında indirin.

---

## Proje Yapısı

```
soru-tekrar-bulucu/
├── main.py          # FastAPI — endpoint'ler, iş yönetimi, SSE ilerleme akışı
├── ocr_engine.py    # OCR mantığı: normalleştirme, benzerlik, gruplama, rapor
├── static/
│   └── index.html   # Tek sayfalık arayüz (HTML + CSS + JS, derleme adımı yok)
├── temp/            # Geçici yükleme dizini (otomatik oluşturulur ve temizlenir)
├── baslat.bat       # Windows için tek tıkla başlatma betiği
├── requirements.txt
└── README.md
```

---

## Sık Karşılaşılan Sorunlar

**`nvidia-smi` komutu çalışıyor ama uygulama GPU'yu görmüyor**  
PyTorch'un CUDA sürümü ile sistemdeki CUDA sürümü uyuşmuyor olabilir. Aşağıdaki komutun `True` döndürmesi gerekir:
```bash
python -c "import torch; print(torch.cuda.is_available())"
```
`False` dönüyorsa PyTorch'u doğru CUDA index URL'siyle yeniden kurun.

**İlk analizde çok uzun süre bekliyorum**  
EasyOCR dil modellerini indiriyor olabilir (~400 MB). İnternet bağlantınızı kontrol edin; indirme tamamlandıktan sonraki analizler çok daha hızlı tamamlanır.

**`uvicorn` komutu tanınmıyor**  
Sanal ortamı etkinleştirmeyi unutmuş olabilirsiniz. `venv\Scripts\activate` (Windows) veya `source venv/bin/activate` (macOS/Linux) komutunu çalıştırın.

**`baslat.bat` çift tıklayınca hemen kapanıyor**  
`baslat.bat` dosyasına sağ tıklayıp **"Yönetici olarak çalıştır"** seçeneğini deneyin. Veya Komut İstemi'ni açıp `cd` komutuyla proje klasörüne gidin ve `baslat.bat` yazın.

**Analiz çok yavaş**  
CPU kullanılıyordur. GPU kurulumu için yukarıdaki "Adım 4 — PyTorch'u Kurun" bölümünü izleyin.

---

## Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
