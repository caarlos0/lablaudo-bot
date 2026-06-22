#!/usr/bin/env python3
"""Lab results crawler for patient portal."""

import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Browser-like User-Agent so Cloudflare doesn't serve a bot-challenge page
# (the default python-requests UA gets blocked from datacenter IPs).
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class ExamDetail:
    """Details of a single exam from the results page."""
    name: str
    status: str
    expected_date: Optional[datetime] = None


_PREVISAO_RE = re.compile(
    r'Previs[aã]o de entrega:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})'
)


class LabCrawler:
    """Crawler for lab results portal."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        self.base_url = "https://lablaudo.com.br"
        self.login_url = f"{self.base_url}/acesso_paciente"
        self.results_url = None
        self.last_error: Optional[str] = None

    @staticmethod
    def _http_error_message(status: int) -> str:
        """Return a user-friendly Portuguese message for an HTTP error status."""
        if status in (401, 403):
            return (
                "O portal recusou o acesso (possível bloqueio ou proteção "
                "anti-bot). Tente novamente mais tarde."
            )
        if status == 429:
            return "Muitas tentativas. Aguarde alguns minutos e tente novamente."
        if 500 <= status < 600:
            return (
                f"O portal está com problemas no momento (HTTP {status}). "
                "Tente novamente mais tarde."
            )
        return (
            f"O portal retornou um erro inesperado (HTTP {status}). "
            "Tente novamente mais tarde."
        )
    
    def _is_row_green(self, row) -> bool:
        """Check if a single row indicates results are ready (green)."""
        style = row.get('style', '').lower()
        class_attr = ' '.join(row.get('class', [])).lower()
        bgcolor = row.get('bgcolor', '').lower()
        
        # Look for cells with green background or status indicators
        cells = row.find_all('td')
        cell_green = False
        for cell in cells:
            cell_style = cell.get('style', '').lower()
            cell_class = ' '.join(cell.get('class', [])).lower()
            cell_text = cell.get_text().strip().lower()
            
            # Check for green indicators in cell
            if (
                'green' in cell_style or 'green' in cell_class or
                '#00ff00' in cell_style or '#0f0' in cell_style or
                'rgb(0,255,0)' in cell_style or
                'background-color:green' in cell_style.replace(' ', '') or
                'success' in cell_class or 'ready' in cell_class or
                'disponivel' in cell_text or 'pronto' in cell_text or
                'liberado' in cell_text or 'concluido' in cell_text
            ):
                cell_green = True
                break
        
        # Check for green indicators in row style, class, or bgcolor attribute
        return (
            'green' in style or 
            'green' in class_attr or
            '#00ff00' in style or
            '#0f0' in style or
            'rgb(0,255,0)' in style or
            'background-color:green' in style.replace(' ', '') or
            'success' in class_attr or
            'ready' in class_attr.lower() or
            'disponivel' in class_attr.lower() or
            cell_green or
            '#8ff08f' in bgcolor or  # Light green background
            'green' in bgcolor
        )
    
    def login(self, username: str, password: str) -> bool:
        """Login to the patient portal.

        On failure, returns False and sets ``self.last_error`` to a
        user-friendly Portuguese message explaining what went wrong.
        """
        self.last_error = None
        logger.info("Attempting login for %s", username)

        # Fetch the login page.
        try:
            response = self.session.get(self.login_url, timeout=30)
        except requests.Timeout:
            self.last_error = (
                "O portal demorou demais para responder. Tente novamente mais tarde."
            )
            logger.warning("Login failed for %s: timeout fetching login page", username)
            return False
        except requests.RequestException as exc:
            self.last_error = (
                "Não consegui conectar ao portal. Verifique sua conexão e "
                "tente novamente."
            )
            logger.warning(
                "Login failed for %s: error fetching login page: %s", username, exc
            )
            return False

        logger.debug(
            "Login page for %s: status=%s server=%s cf-ray=%s",
            username,
            response.status_code,
            response.headers.get("server"),
            response.headers.get("cf-ray"),
        )

        if response.status_code != 200:
            self.last_error = self._http_error_message(response.status_code)
            logger.warning(
                "Login failed for %s: login page returned HTTP %s "
                "(server=%s, cf-ray=%s)",
                username,
                response.status_code,
                response.headers.get("server"),
                response.headers.get("cf-ray"),
            )
            return False

        soup = BeautifulSoup(response.text, 'html.parser')
        form = soup.find('form')

        if not form:
            self.last_error = (
                "O portal está bloqueando o acesso automatizado no momento "
                "(proteção anti-bot). Tente novamente mais tarde."
            )
            logger.warning(
                "Login failed for %s: no <form> on login page "
                "(status=%s, server=%s, cf-ray=%s) - likely a Cloudflare "
                "bot-challenge page served to this IP/User-Agent",
                username,
                response.status_code,
                response.headers.get("server"),
                response.headers.get("cf-ray"),
            )
            return False

        # Prepare login data - try common field names
        login_data = {
            'username': username,
            'password': password,
            'identificacao': username,  # Portuguese field name
            'senha': password,          # Portuguese field name
        }

        # Extract any hidden form fields
        for hidden_input in form.find_all('input', type='hidden'):
            name = hidden_input.get('name')
            value = hidden_input.get('value', '')
            if name:
                login_data[name] = value

        # Check actual form field names
        for input_field in form.find_all('input'):
            field_name = input_field.get('name', '')
            field_type = input_field.get('type', '')
            if field_type in ['text', 'email', 'number'] and not login_data.get(field_name):
                login_data[field_name] = username
            elif field_type == 'password' and not login_data.get(field_name):
                login_data[field_name] = password

        # Submit login form
        action_url = form.get('action', self.login_url)
        if action_url.startswith('/'):
            action_url = self.base_url + action_url
        elif not action_url.startswith('http'):
            action_url = self.login_url

        # Log field names only (never values) to avoid leaking the password.
        logger.debug(
            "Submitting login for %s to %s with fields %s",
            username,
            action_url,
            sorted(login_data.keys()),
        )

        try:
            login_response = self.session.post(
                action_url,
                data=login_data,
                allow_redirects=True,
                timeout=30,
            )
        except requests.Timeout:
            self.last_error = (
                "O portal demorou demais para responder. Tente novamente mais tarde."
            )
            logger.warning("Login failed for %s: timeout submitting login", username)
            return False
        except requests.RequestException as exc:
            self.last_error = (
                "Não consegui conectar ao portal. Verifique sua conexão e "
                "tente novamente."
            )
            logger.warning(
                "Login failed for %s: error submitting login: %s", username, exc
            )
            return False

        if login_response.status_code != 200:
            self.last_error = self._http_error_message(login_response.status_code)
            logger.warning(
                "Login failed for %s: login submit returned HTTP %s (url=%s)",
                username,
                login_response.status_code,
                login_response.url,
            )
            return False

        # Check if login was successful. A valid login redirects away from the
        # login page (e.g. to /laudos/<id>); rejected credentials keep us on the
        # /acesso_paciente login page, so the final URL is the reliable signal.
        final_path = urlparse(login_response.url).path.rstrip('/')
        login_path = urlparse(self.login_url).path.rstrip('/')
        still_on_login = final_path == login_path or final_path.startswith(login_path + '/')

        if not still_on_login:
            # Store the current URL for results checking
            self.results_url = login_response.url
            logger.info("Login succeeded for %s (url=%s)", username, login_response.url)
            return True

        self.last_error = (
            "Não foi possível entrar. Verifique se o usuário e a senha estão "
            "corretos."
        )
        logger.warning(
            "Login failed for %s: still on login page after submit "
            "(status=%s, url=%s) - credentials likely incorrect",
            username,
            login_response.status_code,
            login_response.url,
        )
        return False
    
    def check_results(self) -> bool:
        """Check if all results have green background (ready)."""
        try:
            # Use the results URL from login, or try to find results page
            if self.results_url:
                response = self.session.get(self.results_url)
            else:
                response = self.session.get(self.login_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for results table or results page link if not already there
            if not self.results_url or 'entrar' in response.text.lower():
                results_link = soup.find('a', href=lambda x: x and ('resultado' in x.lower() or 'exame' in x.lower() or 'laudo' in x.lower()))
                if results_link:
                    results_url = results_link.get('href')
                    if results_url.startswith('/'):
                        results_url = self.base_url + results_url
                    elif not results_url.startswith('http'):
                        results_url = self.base_url + '/' + results_url
                    
                    response = self.session.get(results_url)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all table rows (tr elements)
            table_rows = soup.find_all('tr')
            
            if not table_rows:
                return False
            
            results_rows = []
            for row in table_rows:
                # Skip header rows, empty rows, or signature rows
                if (row.find('th') or not row.find('td') or 
                    'visualizar laudo' in row.get_text().lower() or
                    'assinatura' in row.get_text().lower()):
                    continue
                results_rows.append(row)
            
            if not results_rows:
                return False
            
            # Check if all rows have green background
            all_green = True
            for row in results_rows:
                if not self._is_row_green(row):
                    all_green = False
                    break
            
            return all_green
            
        except requests.RequestException:
            return False
    
    def get_exam_details(self) -> List[ExamDetail]:
        """Extract exam details including expected delivery dates from results page."""
        try:
            if self.results_url:
                response = self.session.get(self.results_url)
            else:
                response = self.session.get(self.login_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            exams: List[ExamDetail] = []

            # Find the "Exames do Laudo" table only, skip "Laudos de médicos" etc.
            exam_table = None
            for caption in soup.find_all('caption'):
                if 'exames' in caption.get_text().lower():
                    exam_table = caption.find_next('table')
                    break

            if not exam_table:
                return exams

            for row in exam_table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue

                name = cells[0].get_text().strip()
                status_cell = cells[1]
                status_div = status_cell.find('div')
                status = status_div.get_text().strip() if status_div else status_cell.get_text().strip()

                expected_date: Optional[datetime] = None
                label = status_cell.find('label')
                if label:
                    match = _PREVISAO_RE.search(label.get_text())
                    if match:
                        try:
                            expected_date = datetime.strptime(match.group(1), '%d/%m/%Y %H:%M')
                        except ValueError:
                            pass

                exams.append(ExamDetail(name=name, status=status, expected_date=expected_date))

            return exams
        except requests.RequestException:
            return []
    
    def get_pdf_link(self) -> Optional[str]:
        """Get the PDF download link from the results page."""
        try:
            # Use the results URL from login
            if self.results_url:
                response = self.session.get(self.results_url)
            else:
                response = self.session.get(self.login_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for links with specific text patterns
            target_texts = ['visualizar laudo', 'baixar', 'download']
            
            # Search for links that contain the target text
            for link in soup.find_all('a', href=True):
                link_text = link.get_text().strip().lower()
                href = link.get('href')
                
                # Check if link text matches our patterns
                if any(target in link_text for target in target_texts):
                    # Build full URL
                    if href.startswith('/'):
                        pdf_url = self.base_url + href
                    elif not href.startswith('http'):
                        pdf_url = self.base_url + '/' + href
                    else:
                        pdf_url = href
                    
                    return pdf_url
            
            # Also look for any links containing /get_laudo
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if '/get_laudo' in href:
                    if href.startswith('/'):
                        pdf_url = self.base_url + href
                    elif not href.startswith('http'):
                        pdf_url = self.base_url + '/' + href
                    else:
                        pdf_url = href
                    
                    return pdf_url
            
            return None
            
        except requests.RequestException:
            return None
    
    def download_pdf(self, pdf_url: str) -> Optional[Tuple[bytes, str]]:
        """Download PDF using the logged in session and return content with filename."""
        try:
            # Use the authenticated session to download
            response = self.session.get(pdf_url)
            response.raise_for_status()
            
            # Check if we got PDF content directly
            content_type = response.headers.get('content-type', '').lower()
            
            if 'pdf' in content_type:
                # Direct PDF response
                pass
            elif 'html' in content_type:
                # HTML response - look for embedded PDF data
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for base64 PDF data in object/param tags
                pdf_object = soup.find('object', {'type': 'application/pdf'})
                if pdf_object:
                    base64_param = pdf_object.find('param', {'id': 'base64-param'})
                    if base64_param:
                        base64_data = base64_param.get('value', '')
                        if base64_data:
                            try:
                                import base64
                                pdf_content = base64.b64decode(base64_data)
                                
                                # Verify it's actually a PDF
                                if pdf_content.startswith(b'%PDF'):
                                    filename = "lab_results.pdf"
                                    return pdf_content, filename
                            except Exception:
                                pass
                
                # Look for iframe with PDF source
                pdf_iframe = soup.find('iframe', {'type': 'application/pdf'})
                if pdf_iframe and pdf_iframe.get('src'):
                    iframe_src = pdf_iframe.get('src')
                    if iframe_src.startswith('/'):
                        iframe_src = self.base_url + iframe_src
                    elif not iframe_src.startswith('http'):
                        iframe_src = self.base_url + '/' + iframe_src
                    
                    # Try to download from iframe source
                    iframe_response = self.session.get(iframe_src)
                    iframe_response.raise_for_status()
                    
                    if iframe_response.content.startswith(b'%PDF'):
                        filename = "lab_results.pdf"
                        return iframe_response.content, filename
                
                # Look for direct PDF links in the HTML
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if href.endswith('.pdf') or 'pdf' in href.lower():
                        if href.startswith('/'):
                            pdf_link_url = self.base_url + href
                        elif not href.startswith('http'):
                            pdf_link_url = self.base_url + '/' + href
                        else:
                            pdf_link_url = href
                        
                        # Download the PDF
                        pdf_response = self.session.get(pdf_link_url)
                        pdf_response.raise_for_status()
                        
                        if pdf_response.content.startswith(b'%PDF'):
                            filename = "lab_results.pdf"
                            return pdf_response.content, filename
                
                return None
            else:
                # Check if content looks like PDF
                if not response.content.startswith(b'%PDF'):
                    return None
            
            # If we get here, response.content should be PDF
            if not response.content.startswith(b'%PDF'):
                return None
            
            # Generate filename
            filename = "lab_results.pdf"
            
            # Try to get filename from Content-Disposition header
            content_disposition = response.headers.get('content-disposition', '')
            if 'filename=' in content_disposition:
                try:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
                except:
                    pass
            
            # If no filename from headers, try to extract from URL
            if filename == "lab_results.pdf" and pdf_url:
                url_parts = pdf_url.split('/')
                for part in reversed(url_parts):
                    if '.' in part and not part.startswith('?'):
                        filename = part.split('?')[0]  # Remove query parameters
                        break
            
            # Ensure filename has .pdf extension
            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            
            return response.content, filename
            
        except requests.RequestException:
            return None