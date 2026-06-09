"""
Invio notifiche email via SendGrid.
"""

import os
import logging
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
NOTIFICA_EMAIL = os.getenv("NOTIFICA_EMAIL", "matteo.pirovano@flatmatesagency.com")


def invia_notifica_prenotazione(prenotazione: dict) -> bool:
    """
    Invia un'email di notifica prenotazione via SendGrid.

    Args:
        prenotazione: dict con i dati della prenotazione (da crea_prenotazione_multipla)

    Returns:
        True se l'invio è riuscito, False altrimenti.
    """
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY non configurata — email non inviata")
        return False

    try:
        # Formatta i dati della prenotazione
        periodo = f"{prenotazione['periodo']['data_inizio']} → {prenotazione['periodo']['data_fine']}"
        if prenotazione.get('periodo', {}).get('ora_inizio'):
            periodo += f" ({prenotazione['periodo']['ora_inizio']}–{prenotazione['periodo'].get('ora_fine', '')})"

        # Costruisce il riepilogo articoli
        articoli_html = ""
        for articolo in prenotazione.get('articoli', []):
            codici = ", ".join(p['codice'] for p in articolo.get('assegnati', []))
            articoli_html += f"""
            <tr>
              <td style="padding: 8px; border-bottom: 1px solid #eee;">{articolo['quantita']}× {articolo['tipo']}</td>
              <td style="padding: 8px; border-bottom: 1px solid #eee; font-family: monospace; font-size: 12px; color: #666;">{codici}</td>
            </tr>
            """

        # Email in HTML
        html_content = f"""
        <html>
          <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 20px; border-radius: 8px;">

              <h2 style="color: #2c3e50; border-bottom: 3px solid #6c63ff; padding-bottom: 12px;">
                ✅ Nuova Prenotazione Registrata
              </h2>

              <div style="background: white; padding: 16px; border-radius: 6px; margin: 16px 0;">
                <p><strong>ID Prenotazione:</strong> {prenotazione['gruppo_id']}</p>
                <p><strong>Progetto:</strong> {prenotazione.get('progetto', '—') or '—'}</p>
                <p><strong>Chi prenota:</strong> {prenotazione.get('prenotato_da', '—') or '—'}</p>
                <p><strong>Periodo:</strong> 📅 {periodo}</p>
                {f"<p><strong>Note:</strong> {prenotazione.get('note')}</p>" if prenotazione.get('note') else ""}
              </div>

              <div style="background: white; padding: 16px; border-radius: 6px; margin: 16px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Attrezzatura ({prenotazione['totale_pezzi']} pezzi)</h3>
                <table style="width: 100%; border-collapse: collapse;">
                  <thead>
                    <tr style="background: #f5f5f5;">
                      <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Tipo</th>
                      <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Codici assegnati</th>
                    </tr>
                  </thead>
                  <tbody>
                    {articoli_html}
                  </tbody>
                </table>
              </div>

              <div style="text-align: center; color: #888; font-size: 12px; margin-top: 24px; border-top: 1px solid #eee; padding-top: 16px;">
                <p>FlatBot — Assistente Flatmates<br/>
                Generato il {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
              </div>

            </div>
          </body>
        </html>
        """

        # Invia l'email
        message = Mail(
            from_email=NOTIFICA_EMAIL,  # mittente (SendGrid richiede email verificata)
            to_emails=NOTIFICA_EMAIL,
            subject=f"📦 Nuova Prenotazione – {prenotazione.get('progetto', 'Senza nome')}",
            html_content=html_content,
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        logger.info(f"Email inviata (status {response.status_code}) a {NOTIFICA_EMAIL}")
        return response.status_code in [200, 202]

    except Exception as e:
        logger.error(f"Errore invio email: {e}")
        return False
