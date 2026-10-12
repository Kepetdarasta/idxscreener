import type { Metadata } from "next";

export const metadata: Metadata = { title: "Panduan · Siklus Saham IDX" };

// Angka bawaan di bawah ini harus sama dengan config.py. Jika Anda mengubah parameter di config.py,
// ubah juga di sini supaya panduan tetap benar.
const C = {
  bbPercentile: 25, bbLookback: 30, obvDays: 10,
  breakoutDays: 5, markupVolume: "1,5", volAvgDays: 20,
  distRise: 2, distDrop: 10, distDays: 5,
  markdownDrop: 5, markdownDays: 3, markdownVolume: "1,2",
  rangeDays: 20, atrDays: 14, minRR: "1,2",
  maFast: 5, maSlow: 20, macd: "12, 26, 9", confirmWindow: 10,
};

const SECTIONS = [
  ["ringkasan", "Ringkasan"], ["admd", "Siklus ADMD"], ["cross", "Cross MA"],
  ["kombinasi", "Kombinasi"], ["strategi", "Strategi: masuk, hold, keluar"],
  ["membaca", "Membaca dashboard"], ["batasan", "Batasan"],
] as const;

export default function Panduan() {
  return (
    <main className="guide">
      <h1>Panduan</h1>
      <p className="muted lead">Cara kerja setiap tab dan aturan yang dipakai alat ini untuk masuk, menahan, dan keluar dari sebuah saham.</p>

      <nav className="toc" aria-label="Isi panduan">
        {SECTIONS.map(([id, label]) => <a key={id} className="chip" href={`#${id}`}>{label}</a>)}
      </nav>

      <div className="callout warn">
        <p><b>Penting.</b> Panduan ini menjelaskan cara kerja alat dan aturan yang dipakainya. Isinya bukan saran investasi. Sinyal dihitung otomatis dari harga dan volume, belum diuji akurasinya secara historis, dan keputusan beserta risikonya tetap ada pada Anda.</p>
      </div>

      {/* ───────────────────────── RINGKASAN ───────────────────────── */}
      <section id="ringkasan" className="guide-sec">
        <h2>Ringkasan</h2>
        <p>Dashboard menyaring 45 saham LQ45 dengan dua sistem yang saling melengkapi, lalu menyandingkan hasilnya.</p>
        <div className="scroll"><table>
          <thead><tr><th>Tab</th><th>Pertanyaan yang dijawab</th><th>Horizon</th></tr></thead>
          <tbody>
            <tr><td><b>Siklus ADMD</b></td><td>Saham ini sedang berada di fase apa?</td><td>Menengah hingga panjang (pekan sampai bulan)</td></tr>
            <tr><td><b>Cross MA</b></td><td>Kapan masuk, dan sampai kapan ditahan?</td><td>Swing (pekan)</td></tr>
            <tr><td><b>Kombinasi</b></td><td>Apakah kedua sistem berjalan searah?</td><td>Penyaring gabungan</td></tr>
          </tbody>
        </table></div>
        <p className="muted">Semua data adalah harga penutupan harian dari Yahoo Finance. Data diperbarui otomatis pada hari bursa sekitar pukul 17:15 WIB. Dashboard ini tidak real-time.</p>
      </section>

      {/* ───────────────────────── ADMD ───────────────────────── */}
      <section id="admd" className="guide-sec">
        <h2>Siklus ADMD</h2>
        <p>Harga saham cenderung bergerak dalam siklus empat fase, terinspirasi metode Wyckoff:</p>
        <ul>
          <li><b>Akumulasi</b>: pelaku besar mengumpulkan saham secara diam-diam. Harga bergerak sempit dan volatilitas mengecil.</li>
          <li><b>Mark Up</b>: harga keluar dari rentang sempit ke atas, disertai volume besar.</li>
          <li><b>Distribusi</b>: harga mentok atau stagnan sementara volume masih ramai. Saham bisa sedang dilepas ke pasar.</li>
          <li><b>Mark Down</b>: harga turun cepat disertai volume.</li>
        </ul>
        <div className="callout">
          <p>Alat ini tidak mengenali pola Wyckoff secara formal (misalnya Spring atau Sign of Strength). Ia memakai ukuran sederhana dari harga dan volume sebagai pendekatan, sehingga hasilnya perlu dibaca sebagai petunjuk, bukan kepastian.</p>
        </div>

        <h3>Syarat setiap fase (pengaturan bawaan)</h3>
        <div className="scroll"><table>
          <thead><tr><th>Fase</th><th>Syarat</th><th className="num">Rentang skor</th></tr></thead>
          <tbody>
            <tr><td><i className="dot" style={{ background: "#3fb97f" }} />Akumulasi</td>
              <td className="wrap">Lebar Bollinger Band (20 hari) berada di {C.bbPercentile}% terendah dari {C.bbLookback} hari terakhir, artinya volatilitas menyempit. Kemiringan OBV {C.obvDays} hari terakhir harus positif. Volume yang mengering (di bawah rata-rata {C.volAvgDays} hari) menambah skor.</td>
              <td className="num">75 – 95</td></tr>
            <tr><td><i className="dot" style={{ background: "#4a9eff" }} />Mark Up</td>
              <td className="wrap">Memenuhi syarat Akumulasi pada hari yang sama, <em>dan</em> penutupan melampaui harga tertinggi {C.breakoutDays} hari sebelumnya, volume ≥ {C.markupVolume}× rata-rata {C.volAvgDays} hari, dan OBV menyentuh level tertinggi {C.breakoutDays} hari terakhir. Syaratnya berlapis, jadi sinyal ini relatif jarang.</td>
              <td className="num">70 – 90</td></tr>
            <tr><td><i className="dot" style={{ background: "#e89a3c" }} />Distribusi</td>
              <td className="wrap">Perubahan harga {C.distDays} hari antara −{C.distDrop}% dan +{C.distRise}% (stagnan atau turun tipis), dan volume ≥ rata-rata {C.volAvgDays} hari. Kriteria ini longgar, jadi daftar Distribusi bisa cukup ramai.</td>
              <td className="num">50 – 65</td></tr>
            <tr><td><i className="dot" style={{ background: "#e5564b" }} />Mark Down</td>
              <td className="wrap">Harga turun ≥ {C.markdownDrop}% dalam {C.markdownDays} hari, dan volume ≥ {C.markdownVolume}× rata-rata {C.volAvgDays} hari.</td>
              <td className="num">50 – 100</td></tr>
          </tbody>
        </table></div>

        <h3>Skor</h3>
        <p>Skor 0–100 menunjukkan seberapa jelas kriteria sebuah sinyal terpenuhi. Skor <b>bukan probabilitas</b> harga akan naik atau turun. Karena syarat Akumulasi sudah ketat, banyak saham Akumulasi mendapat skor tinggi yang berdekatan, sehingga skor kurang membedakan satu saham dari yang lain. Gunakan skor sebagai pembanding kasar, bukan sebagai peringkat yang presisi.</p>

        <h3>Jika satu saham memenuhi beberapa sinyal</h3>
        <p>Satu saham hanya ditampilkan dalam satu fase per hari, dengan urutan prioritas <b>Mark Down, Mark Up, Distribusi, Akumulasi</b>. Karena Mark Up mensyaratkan Akumulasi, setiap saham Mark Up sebenarnya juga memenuhi Akumulasi, dan yang ditampilkan adalah Mark Up.</p>

        <h3>Trade setup pada sinyal Mark Up</h3>
        <p>Untuk saham Mark Up, alat ini menghitung titik acuan:</p>
        <ul>
          <li><b>Entry</b>: harga penutupan pada hari sinyal.</li>
          <li><b>Stop loss</b>: di bawah level resistance yang baru ditembus (harga tertinggi {C.breakoutDays} hari sebelumnya) dikurangi 1× ATR({C.atrDays}), dan tidak lebih rendah dari dasar range {C.rangeDays} hari.</li>
          <li><b>Target</b>: entry ditambah tinggi range {C.rangeDays} hari sebelum breakout.</li>
          <li><b>Risk : Reward</b>: jarak ke target dibagi jarak ke stop. Mark Up dengan RR di bawah {C.minRR} tidak ditampilkan sebagai Mark Up; saham itu tetap tampil sebagai Akumulasi.</li>
        </ul>
        <p className="muted">Setiap perubahan fase dicatat. Di halaman saham, pita warna pada chart menunjukkan fase yang pernah dilalui.</p>
      </section>

      {/* ───────────────────────── CROSS MA ───────────────────────── */}
      <section id="cross" className="guide-sec">
        <h2>Cross MA</h2>
        <p>Tab ini melacak posisi swing dari persilangan rata-rata bergerak yang dikonfirmasi MACD. Berbeda dengan ADMD, tab ini punya <b>status</b>: sebuah posisi dibuka, ditahan, lalu ditutup.</p>

        <h3>Aturan</h3>
        <ol>
          <li><b>Masuk</b>: MA{C.maFast} menembus MA{C.maSlow} ke atas <em>dan</em> MACD ({C.macd}) golden cross, keduanya terjadi dalam jendela {C.confirmWindow} hari bursa. Urutannya boleh salah satu lebih dulu, karena MACD sering berbalik arah lebih awal daripada MA. Harga acuan adalah penutupan hari ketika syarat kedua terpenuhi.</li>
          <li><b>Hold</b>: posisi ditahan selama syarat keluar belum lengkap.</li>
          <li><b>Keluar</b>: MA{C.maFast} berada di bawah MA{C.maSlow} <em>dan</em> MACD dead cross, keduanya terjadi setelah tanggal masuk. Keluar hanya bila dua-duanya terpenuhi.</li>
        </ol>

        <h3>Status di tab</h3>
        <div className="scroll"><table>
          <thead><tr><th>Status</th><th>Artinya</th></tr></thead>
          <tbody>
            <tr><td><span className="tag">Menunggu MACD</span></td><td className="wrap">MA{C.maFast} sudah menembus MA{C.maSlow} ke atas, tetapi MACD belum golden cross. Dibatalkan bila MA{C.maFast} kembali di bawah MA{C.maSlow}, atau kedaluwarsa setelah {C.confirmWindow} hari bursa.</td></tr>
            <tr><td><span className="tag ok">Tren masih utuh</span></td><td className="wrap">Posisi sedang di-hold dan belum ada syarat keluar yang terpenuhi.</td></tr>
            <tr><td><span className="tag warn">Peringatan</span></td><td className="wrap">Posisi di-hold, tetapi <em>satu</em> syarat keluar sudah terjadi (MA{C.maFast} di bawah MA{C.maSlow}, atau MACD dead cross). Menurut aturan, posisi belum ditutup karena syarat keduanya belum terpenuhi.</td></tr>
            <tr><td>Tertutup</td><td className="wrap">Kedua syarat keluar terpenuhi. Posisi masuk ke riwayat beserta return dan hasilnya.</td></tr>
          </tbody>
        </table></div>

        <h3>Hal yang perlu diperhatikan</h3>
        <ul>
          <li><b>Tidak ada stop loss</b> dalam aturan ini. Kolom <b>Terdalam</b> menunjukkan penurunan terdalam dari harga masuk selama posisi dipegang, supaya risikonya terlihat.</li>
          <li><b>Rawan sinyal palsu saat harga sideways.</b> Persilangan MA dan MACD sering muncul bolak-balik pada harga yang bergerak mendatar, sehingga posisi bisa cepat terbuka dan tertutup dengan hasil kecil atau rugi.</li>
          <li>Harga masuk dan keluar pada statistik riwayat adalah penutupan hari sinyal, tanpa biaya transaksi. Pada praktiknya Anda bertransaksi keesokan harinya, dengan harga yang bisa berbeda.</li>
        </ul>
      </section>

      {/* ───────────────────────── KOMBINASI ───────────────────────── */}
      <section id="kombinasi" className="guide-sec">
        <h2>Kombinasi</h2>
        <p>Tab ini menyandingkan fase ADMD hari ini dengan posisi swing yang sedang berjalan. Saham yang kedua sistemnya searah punya dukungan lebih banyak daripada yang hanya lolos salah satu.</p>
        <div className="scroll"><table>
          <thead><tr><th>Kategori</th><th>Syarat</th></tr></thead>
          <tbody>
            <tr><td><span className="tag ok">Selaras kuat</span></td><td className="wrap">Fase Akumulasi atau Mark Up, dan posisi swing sedang di-hold tanpa peringatan keluar.</td></tr>
            <tr><td><span className="tag">Selaras awal</span></td><td className="wrap">Fase Akumulasi atau Mark Up, dan MA{C.maFast} sudah cross up tetapi MACD belum golden cross.</td></tr>
            <tr><td><span className="tag">Fase mendukung</span></td><td className="wrap">Fase Akumulasi atau Mark Up, tetapi belum ada persilangan swing yang terkonfirmasi.</td></tr>
            <tr><td><span className="tag warn">Waspada</span></td><td className="wrap">Posisi swing masih di-hold, tetapi ada peringatan keluar, atau fase ADMD sudah memburuk menjadi Distribusi atau Mark Down.</td></tr>
          </tbody>
        </table></div>
        <p className="muted">Saham di luar keempat kategori ini tidak ditampilkan. Daftar yang pendek adalah hal yang wajar, karena fungsi tab ini memang menyaring.</p>
      </section>

      {/* ───────────────────────── STRATEGI ───────────────────────── */}
      <section id="strategi" className="guide-sec">
        <h2>Strategi: masuk, hold, keluar</h2>
        <p>Bagian ini merangkum aturan yang dipakai alat untuk strategi swing jangka menengah, ditambah hal yang bisa dipertimbangkan saat memakai tab Kombinasi sebagai penyaring.</p>

        <h3>Masuk</h3>
        <p><b>Aturan alat:</b> MA{C.maFast} cross up MA{C.maSlow} dan MACD golden cross dalam {C.confirmWindow} hari bursa. Saat itu terjadi, saham muncul di <b>Sedang di-hold</b> pada tab Cross MA.</p>
        <p><b>Untuk memperkuat keyakinan, cek:</b></p>
        <ul>
          <li>Pada Kombinasi, saham berada di <b>Selaras kuat</b>, atau baru naik dari <b>Selaras awal</b>.</li>
          <li>Fase ADMD adalah Akumulasi atau Mark Up.</li>
          <li>Pada panel detail, harga masih punya ruang sebelum resistance 20 hari, dan checklist teknikal terpenuhi sebagian besar.</li>
          <li>Jika sinyalnya Mark Up, lihat entry, stop, target, dan RR yang dihitung alat.</li>
        </ul>
        <p><b>Pertimbangkan menahan diri bila:</b> fase ADMD adalah Distribusi atau Mark Down, harga sudah naik jauh dari harga acuan sinyal, harga menempel di resistance, atau pasar sedang bergerak mendatar (banyak sinyal palsu). Ingat bahwa harga acuan adalah penutupan hari sinyal, sedangkan Anda baru bisa bertransaksi pada hari berikutnya.</p>

        <h3>Hold</h3>
        <p><b>Aturan alat:</b> tahan selama syarat keluar belum lengkap. Status <span className="tag ok">Tren masih utuh</span> berarti belum ada syarat keluar yang terpenuhi.</p>
        <ul>
          <li><span className="tag warn">Peringatan</span> adalah tanda untuk <b>meninjau ulang</b>, bukan perintah keluar. Satu syarat sudah terjadi, dan satu lagi menentukan.</li>
          <li>Pada Kombinasi, kategori <b>Waspada</b> muncul bila fase ADMD memburuk sementara posisi masih di-hold. Itu tanda dua sistem mulai tidak sejalan.</li>
        </ul>

        <h3>Keluar</h3>
        <p><b>Aturan alat:</b> keluar ketika MA{C.maFast} di bawah MA{C.maSlow} <em>dan</em> MACD dead cross. Saat itu terjadi, posisi pindah ke <b>Riwayat posisi tertutup</b>.</p>
        <p>Karena aturan ini menunggu dua konfirmasi, keluarnya bisa cukup terlambat dan sebagian keuntungan bisa tergerus lebih dulu. Sebagian trader menambahkan aturan sendiri di luar sistem, misalnya batas kerugian pribadi atau mengurangi posisi saat muncul peringatan bersamaan dengan fase Distribusi atau Mark Down. Alat ini tidak melakukannya untuk Anda.</p>

        <h3>Ringkasan tindakan menurut tampilan di dashboard</h3>
        <div className="scroll"><table>
          <thead><tr><th>Yang terlihat</th><th>Artinya</th><th>Yang bisa dipertimbangkan</th></tr></thead>
          <tbody>
            <tr><td className="wrap">Kombinasi: <b>Selaras awal</b></td><td className="wrap">MA sudah cross up, MACD belum</td><td className="wrap">Pantau. Belum ada konfirmasi, jadi belum memenuhi aturan masuk.</td></tr>
            <tr><td className="wrap">Cross MA: posisi baru di <b>Sedang di-hold</b>, Kombinasi: <b>Selaras kuat</b></td><td className="wrap">Aturan masuk terpenuhi dan fase mendukung</td><td className="wrap">Kandidat masuk. Cek panel detail, ruang ke resistance, dan likuiditas.</td></tr>
            <tr><td className="wrap">Sedang di-hold, <b>Tren masih utuh</b></td><td className="wrap">Belum ada syarat keluar</td><td className="wrap">Tetap hold sesuai aturan.</td></tr>
            <tr><td className="wrap">Peringatan: MA{C.maFast} di bawah MA{C.maSlow}, atau MACD dead cross</td><td className="wrap">Satu dari dua syarat keluar sudah terjadi</td><td className="wrap">Tinjau ulang dan siapkan rencana keluar.</td></tr>
            <tr><td className="wrap">Kombinasi: <b>Waspada</b> (fase Distribusi atau Mark Down)</td><td className="wrap">Swing dan ADMD tidak searah</td><td className="wrap">Tinjau ulang posisi. Ini sinyal peringatan dini di luar aturan keluar resmi.</td></tr>
            <tr><td className="wrap">Posisi pindah ke <b>Tertutup</b></td><td className="wrap">Kedua syarat keluar terpenuhi</td><td className="wrap">Menurut aturan, saatnya keluar.</td></tr>
          </tbody>
        </table></div>

        <h3>Rutinitas harian yang sederhana</h3>
        <ol>
          <li>Setelah data diperbarui (sekitar pukul 17:15 WIB), buka <b>Kombinasi</b> dan lihat kategori Waspada untuk saham yang Anda pegang.</li>
          <li>Buka <b>Cross MA</b> untuk memeriksa status posisi dan peringatan.</li>
          <li>Lihat kategori Selaras kuat dan Selaras awal untuk kandidat baru.</li>
          <li>Buka halaman saham yang menarik, dan periksa chart, level support dan resistance, serta checklist teknikal.</li>
        </ol>

        <h3>Yang tidak dilakukan alat ini</h3>
        <ul>
          <li>Stop loss otomatis dan penentuan ukuran posisi.</li>
          <li>Memperhitungkan biaya transaksi dan pajak.</li>
          <li>Memperhitungkan selisih harga eksekusi, gap harga pembukaan, atau likuiditas saat Anda membeli dan menjual.</li>
          <li>Menilai fundamental, berita, atau aksi korporasi seperti dividen dan stock split.</li>
        </ul>
      </section>

      {/* ───────────────────────── MEMBACA DASHBOARD ───────────────────────── */}
      <section id="membaca" className="guide-sec">
        <h2>Membaca dashboard</h2>
        <div className="scroll"><table>
          <thead><tr><th>Istilah</th><th>Penjelasan</th></tr></thead>
          <tbody>
            <tr><td><b>Skor</b></td><td className="wrap">Kejelasan kriteria ADMD terpenuhi, skala 0–100. Bukan probabilitas.</td></tr>
            <tr><td><b>RR</b> (Risk : Reward)</td><td className="wrap">Jarak ke target dibagi jarak ke stop, hanya untuk sinyal Mark Up. Makin besar makin menguntungkan secara hitungan, namun tidak menjamin target tercapai.</td></tr>
            <tr><td><b>Hari ini</b></td><td className="wrap">Perubahan harga penutupan terakhir dibanding penutupan sebelumnya.</td></tr>
            <tr><td><b>Terdalam</b></td><td className="wrap">Penurunan terdalam dari harga masuk selama posisi swing dipegang.</td></tr>
            <tr><td><b>Support dan Resistance 20 hari</b></td><td className="wrap">Harga terendah dan tertinggi 20 hari bursa terakhir. Ini ukuran sederhana, bukan analisis level yang mendalam.</td></tr>
            <tr><td><b>Checklist teknikal</b></td><td className="wrap">Tujuh pemeriksaan sederhana (higher low, higher high, volume saat naik, harga di atas MA20, basis konsolidasi, kekuatan relatif terhadap IHSG, dan RR). Berguna sebagai pengingat, bukan metodologi baku.</td></tr>
            <tr><td><b>Heatmap sektor</b></td><td className="wrap">Perubahan harga satu hari per saham, dikelompokkan per sektor. Rata-rata sektor dihitung dengan bobot sama, bukan berdasarkan kapitalisasi pasar.</td></tr>
            <tr><td><b>Watchlist</b></td><td className="wrap">Tersimpan di browser Anda saja, tanpa login. Tidak ikut berpindah ke perangkat atau browser lain.</td></tr>
          </tbody>
        </table></div>
      </section>

      {/* ───────────────────────── BATASAN ───────────────────────── */}
      <section id="batasan" className="guide-sec">
        <h2>Batasan</h2>
        <ul>
          <li><b>Akurasi belum teruji.</b> Belum ada backtest yang membuktikan bahwa sinyal ADMD atau kategori Kombinasi lebih sering benar daripada saham biasa. Statistik riwayat di tab Cross MA berasal dari simulasi aturan pada data yang tersedia, dan hasil historis tidak menjamin hasil ke depan.</li>
          <li><b>Cakupan terbatas.</b> Hanya 45 saham LQ45 yang disaring, memakai daftar anggota yang berlaku sekarang.</li>
          <li><b>Kualitas data.</b> Data dari Yahoo Finance bisa terlambat atau keliru, dan tidak menandai suspensi atau aksi korporasi.</li>
          <li><b>Hanya harga dan volume.</b> Tidak ada data fundamental, berita, ataupun aktivitas investor asing.</li>
        </ul>
        <div className="callout warn">
          <p>Alat ini membantu menyaring dan mengorganisasi informasi, bukan menggantikan penilaian Anda. Untuk keputusan investasi yang sesuai dengan kondisi keuangan Anda, pertimbangkan berkonsultasi dengan penasihat keuangan berlisensi.</p>
        </div>
      </section>
    </main>
  );
}
