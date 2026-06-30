# Deribit SOL & HYPE Opsiyon Takip Sistemi

Türkiye'den Deribit'e doğrudan erişim engelli olduğu için veri çekme işini
GitHub Actions'a (ABD/AB sunucuları) devrediyoruz. Sen sadece sonucu
`dashboard.html` ile lokalden okuyorsun.

## Kurulum (~5 dakika, tek seferlik)

1. **GitHub'da yeni bir public repo aç** (örn. `deribit-options-tracker`).

2. **Bu üç dosyayı/klasör yapısını repo'ya yükle** (klasör yollarını birebir koru):
   ```
   deribit-options-tracker/
   ├── poll_deribit.py
   └── .github/
       └── workflows/
           └── poll.yml
   ```
   (`dashboard.html`'i repo'ya koymana gerek yok — sadece kendi bilgisayarında tutman yeterli.)

   En kolay yol: repo sayfasında "Add file → Upload files" ile sürükle-bırak.
   `.github/workflows/poll.yml` dosyasını yüklerken GitHub klasör yapısını
   otomatik algılar; yolu elle yazman gerekirse dosya adını
   `.github/workflows/poll.yml` olarak gir.

3. **Workflow'u ilk kez elle tetikle:**
   Repo → **Actions** sekmesi → **Poll Deribit Options Data** → **Run workflow**.
   ~30 saniye içinde çalışır ve repo'da `data/latest.json` + `data/history.csv`
   dosyaları otomatik oluşur. Bundan sonra GitHub her 15 dakikada bir kendiliğinden çalıştırır.

4. **`dashboard.html`'i bilgisayarında çift tıklayarak aç.**
   Sağ üstteki **⚙ Repo Ayarı** kısmına:
   - GitHub kullanıcı adın
   - Repo adın (örn. `deribit-options-tracker`)
   - Branch: `main`

   gir, **Kaydet & Yükle**'ye bas. Bilgiler tarayıcında saklanır, bir daha
   girmen gerekmez — dosyayı her açtığında otomatik yüklenir.

## Nasıl çalışır

```
GitHub Actions (15 dk'da bir, ABD/AB sunucusu)
   → Deribit API'ye istek atar (Türkiye engeli burada yok)
   → data/latest.json + data/history.csv günceller, repo'ya push eder
        │
        ▼
dashboard.html (senin bilgisayarın, Türkiye, VPN'siz)
   → raw.githubusercontent.com'dan bu iki dosyayı okur
   → 60 saniyede bir kendini tazeler (repo'daki veri 15 dk'da bir değişir)
```

## Notlar

- Veri en fazla ~15 dakika gecikmeli olur (GitHub'ın cron aralığı). Anlık
  tick-by-tick takip için bu yeterli değildir ama "ne kadar hacim dönüyor"
  sorusuna gayet iyi cevap verir.
- `data/history.csv` zamanla büyür; çok uzun vadede (aylar) dosya
  şişebilir — istersen ileride eski satırları periyodik temizleyen bir
  adım ekleyebiliriz.
- Workflow `permissions: contents: write` gerektirir; bu repo ayarlarında
  varsayılan olarak açıktır, ekstra bir şey yapmana gerek yok.
- İstersen `cron: '*/15 * * * *'` satırını `.github/workflows/poll.yml`
  içinde değiştirip aralığı kısaltabilirsin (GitHub'ın pratik minimum
  aralığı ~5 dakikadır, daha sık denersen kuyrukta gecikebilir).
