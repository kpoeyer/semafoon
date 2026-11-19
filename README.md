# 📻 P2000 & Semafoon Web Decoder (RTL-SDR)

Een real-time webinterface om P2000 (hulpverlening) en overige semafoonberichten (KPN Nationaal) te decoderen met een RTL-SDR USB-stick.

## ✨ Kenmerken
- **Web-based:** Te openen via elke browser op poort `5000`
- **Frequentie switcher:** P2000 (`169.650M`), KPN (`172.450M`) of handmatig
- **Zoekwoorden Filter:** Markeer berichten met specifieke trefwoorden
- **CAP-code Lijst:** Volg specifieke eenheden (optioneel met naam via `=`)
- **Automatische Logging:** Matches worden opgeslagen in `p2000_matches.log`
- **Filters geheugen:** Invoer wordt opgeslagen in `filters.json`
- **Autostart:** Draait als systemd service na herstart

## 🚀 Installatie

```bash
git clone https://github.com/JOUW_GEBRUIKERSNAAM/semafoon.git
cd semafoon
chmod +x install.sh
./install.sh
