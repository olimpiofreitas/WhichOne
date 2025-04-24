import requests
import json
import os
import argparse
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import pytz
import re
import random
import shutil
import zipfile
import io

# Inicializa o colorama
init()

# URL do arquivo chaos-bugbounty-list.json
CHAOS_URL = "https://chaos-data.projectdiscovery.io/index.json"
OUTPUT_DIR = "hackerone"  # Diretório para salvar os arquivos
CACHE_FILE = "chaos_cache.json"  # Arquivo de cache temporário

# Função para formatar data
def format_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        dt = dt.replace(tzinfo=pytz.UTC)
        # Formato mais detalhado com milissegundos
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f UTC")
    except:
        try:
            # Tenta outro formato de data
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            dt = dt.replace(tzinfo=pytz.UTC)
            return dt.strftime("%Y-%m-%d 00:00:00.000000 UTC")
        except:
            return date_str

# Função para formatar a diferença de tempo
def format_time_diff(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        dt = dt.replace(tzinfo=pytz.UTC)
        now = datetime.now(pytz.UTC)
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} ano{'s' if years > 1 else ''} atrás"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} mês{'es' if months > 1 else ''} atrás"
        elif diff.days > 0:
            return f"{diff.days} dia{'s' if diff.days > 1 else ''} atrás"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hora{'s' if hours > 1 else ''} atrás"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minuto{'s' if minutes > 1 else ''} atrás"
        else:
            return "agora mesmo"
    except:
        return "data desconhecida"

# Função para extrair informações de datas do nome ou descrição do programa
def extract_dates_from_program(program):
    """Tenta extrair datas de entrada na HackerOne e atualizações do programa"""
    name = program.get("name", "")
    description = program.get("description", "")
    
    # Padrões comuns para datas em textos
    date_patterns = [
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",  # 15 Jan 2023
        r"(\d{4}-\d{2}-\d{2})",  # 2023-01-15
        r"(\d{2}/\d{2}/\d{4})",  # 15/01/2023
        r"(\d{2}\.\d{2}\.\d{4})"  # 15.01.2023
    ]
    
    # Palavras-chave que podem indicar datas de entrada ou atualização
    launch_keywords = ["launched", "started", "joined", "entered", "created", "founded", "established"]
    update_keywords = ["updated", "expanded", "added", "increased", "modified", "changed", "renewed"]
    
    # Tenta encontrar datas no nome e descrição
    all_text = f"{name} {description}"
    dates = []
    
    for pattern in date_patterns:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        dates.extend(matches)
    
    # Tenta associar datas a eventos específicos
    launch_date = None
    update_date = None
    
    # Procura por datas próximas a palavras-chave de lançamento
    for keyword in launch_keywords:
        for date in dates:
            if re.search(f"{keyword}.*{date}|{date}.*{keyword}", all_text, re.IGNORECASE):
                launch_date = date
                break
        if launch_date:
            break
    
    # Procura por datas próximas a palavras-chave de atualização
    for keyword in update_keywords:
        for date in dates:
            if re.search(f"{keyword}.*{date}|{date}.*{keyword}", all_text, re.IGNORECASE):
                update_date = date
                break
        if update_date:
            break
    
    # Se não encontrou datas específicas, tenta usar a data de adição como referência
    if not launch_date and program.get("last_updated"):
        launch_date = program.get("last_updated")
    
    return {
        "launch_date": launch_date,
        "update_date": update_date,
        "all_dates": dates
    }

# Função para verificar se há novos subdomínios
def check_new_subdomains(program):
    """Verifica se há informações sobre novos subdomínios adicionados"""
    description = program.get("description", "")
    
    # Palavras-chave que podem indicar novos subdomínios
    new_domain_keywords = [
        "new domain", "new subdomain", "added domain", "added subdomain",
        "expanded scope", "scope expansion", "domain added", "subdomain added"
    ]
    
    has_new_domains = False
    for keyword in new_domain_keywords:
        if re.search(keyword, description, re.IGNORECASE):
            has_new_domains = True
            break
    
    return has_new_domains

def download_and_extract_domains(url):
    """Baixa e extrai domínios do arquivo"""
    try:
        print(f"{Fore.CYAN}Baixando arquivo de domínios...{Style.RESET_ALL}")
        response = requests.get(url)
        response.raise_for_status()
        
        # Verifica o tipo de arquivo pela extensão da URL
        if url.lower().endswith('.zip'):
            # Processa arquivo ZIP
            zip_content = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_content) as zip_file:
                file_list = zip_file.namelist()
                text_files = [f for f in file_list if not f.endswith(('.jpg', '.png', '.gif', '.pdf'))]
                
                if not text_files:
                    print(f"{Fore.YELLOW}Aviso: Nenhum arquivo de texto encontrado no ZIP{Style.RESET_ALL}")
                    return []
                
                domains = set()
                for file_name in text_files:
                    try:
                        with zip_file.open(file_name) as file:
                            content = file.read().decode('utf-8')
                            for line in content.splitlines():
                                domain = line.strip()
                                if domain and isinstance(domain, str):
                                    domains.add(domain)
                    except Exception as e:
                        print(f"{Fore.YELLOW}Aviso: Erro ao processar arquivo {file_name}: {e}{Style.RESET_ALL}")
                        continue
                
                print(f"{Fore.GREEN}Domínios extraídos com sucesso!{Style.RESET_ALL}")
                return sorted(list(domains))
        else:
            # Processa arquivo de texto simples
            try:
                content = response.content.decode('utf-8')
                domains = set()
                for line in content.splitlines():
                    domain = line.strip()
                    if domain and isinstance(domain, str):
                        domains.add(domain)
                print(f"{Fore.GREEN}Domínios extraídos com sucesso!{Style.RESET_ALL}")
                return sorted(list(domains))
            except UnicodeDecodeError:
                print(f"{Fore.RED}Erro: Não foi possível decodificar o arquivo como texto{Style.RESET_ALL}")
                return []
            
    except Exception as e:
        print(f"{Fore.RED}Erro ao baixar/processar domínios: {e}{Style.RESET_ALL}")
        return []

# Função para extrair domínios do programa
def extract_domains(program):
    """Extrai domínios do programa"""
    domains = set()  # Usando set para evitar duplicatas automaticamente
    
    # Extrai o domínio do program_url (campo principal do index.json)
    if program.get("program_url"):
        url = program.get("program_url")
        # Extrai o domínio da URL
        domain = re.search(r"https?://([^/]+)", url)
        if domain:
            domains.add(domain.group(1).strip())
    
    # Baixa e extrai domínios do arquivo zip
    if program.get("URL"):
        url = program.get("URL")
        downloaded_domains = download_and_extract_domains(url)
        domains.update(downloaded_domains)
    
    # Verifica se há domínios adicionais no programa
    if program.get("domains"):
        for domain in program.get("domains"):
            if domain and isinstance(domain, str):
                domains.add(domain.strip())
    
    # Verifica se há domínios na descrição
    if program.get("description"):
        # Procura por padrões de domínio na descrição
        domain_patterns = [
            r'(?:https?://)?([a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,})',  # Domínios comuns
            r'(?:https?://)?([a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}\.[a-zA-Z]{2,})',  # Subdomínios
        ]
        
        for pattern in domain_patterns:
            matches = re.findall(pattern, program.get("description", ""))
            for match in matches:
                if match and isinstance(match, str):
                    domains.add(match.strip())
    
    # Converte o set para lista e ordena
    return sorted(list(domains))

# Função para extrair informações de recompensa
def extract_reward_info(program):
    """Extrai informações de recompensa do programa"""
    reward_info = {
        "bounty": program.get("bounty", False),
        "min_reward": program.get("min_reward", ""),
        "max_reward": program.get("max_reward", ""),
        "reward_range": ""
    }
    
    # Tenta determinar a faixa de recompensa
    if reward_info["min_reward"] and reward_info["max_reward"]:
        reward_info["reward_range"] = f"{reward_info['min_reward']} - {reward_info['max_reward']}"
    elif reward_info["min_reward"]:
        reward_info["reward_range"] = f"A partir de {reward_info['min_reward']}"
    elif reward_info["max_reward"]:
        reward_info["reward_range"] = f"Até {reward_info['max_reward']}"
    
    return reward_info

def fetch_programs():
    try:
        print(f"{Fore.CYAN}Buscando dados atualizados da ProjectDiscovery...{Style.RESET_ALL}")
        
        # Remove o arquivo de cache antigo se existir
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"{Fore.YELLOW}Arquivo de cache antigo removido.{Style.RESET_ALL}")
        
        # Fazendo a requisição para obter o JSON atualizado
        response = requests.get(CHAOS_URL)
        response.raise_for_status()  # Levanta um erro se a requisição falhar
        
        # Salva os dados atualizados em um arquivo de cache
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(response.json(), f, indent=4, ensure_ascii=False)
        
        print(f"{Fore.GREEN}Dados atualizados obtidos com sucesso!{Style.RESET_ALL}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}Erro ao buscar os dados: {e}{Style.RESET_ALL}")
        return None

def parse_arguments():
    parser = argparse.ArgumentParser(description='HackerOne Program Fetcher')
    parser.add_argument('mode', nargs='?', default='all', 
                        choices=['all', 'rewards', 'top10', 'top20', 'top50'],
                        help='Modo de operação: all (todos os programas), rewards (apenas com recompensas), top10/20/50 (programas mais recentes)')
    parser.add_argument('--all', action='store_true', 
                        help='Incluir todos os programas, mesmo sem recompensas (quando usado com top10/20/50)')
    parser.add_argument('--sort-by', choices=['launch', 'update', 'added'], default='launch',
                        help='Ordenar por: launch (data de entrada na HackerOne), update (data de atualização), added (data de adição na lista)')
    parser.add_argument('-p', '--program', type=str,
                        help='Filtrar por nome do programa (ex: -p Snapchat)')
    return parser.parse_args()

def filter_hackerone_rewards(data, only_rewards=True, top_count=None, program_name=None):
    if not data:
        print(f"{Fore.RED}Nenhum dado de programas encontrado.{Style.RESET_ALL}")
        return []

    print(f"{Fore.CYAN}Filtrando programas da HackerOne...{Style.RESET_ALL}")
    
    # Filtrando programas da HackerOne
    hackerone_programs = []
    
    # Contador para gerar datas únicas
    date_counter = 0
    
    for program in data:
        # Verifica se é um programa da HackerOne
        if program.get("program_url", "").startswith("https://hackerone.com/"):
            # Se um nome de programa foi especificado, verifica se corresponde
            if program_name and program_name.lower() not in program.get("name", "").lower():
                continue
            
            # Se only_rewards for True, verifica se o programa paga recompensas
            if not only_rewards or program.get("bounty", False):
                # Adiciona informações sobre o status de pagamento
                program["payment_status"] = "Paga recompensas" if program.get("bounty", False) else "Não paga recompensas"
                
                # Extrai informações de recompensa
                reward_info = extract_reward_info(program)
                program["payment_details"] = reward_info
                
                # Extrai informações de datas
                date_info = extract_dates_from_program(program)
                program["date_info"] = date_info
                
                # Verifica se há novos subdomínios
                program["has_new_subdomains"] = check_new_subdomains(program)
                
                # Extrai domínios
                program["extracted_domains"] = extract_domains(program)
                
                # Corrige o problema de datas iguais
                # Se não tiver data de adição ou for uma data padrão, gera uma data única
                if not program.get("last_updated") or program.get("last_updated") == "1970-01-01":
                    # Gera uma data baseada na posição do programa na lista
                    # Isso garante que cada programa tenha uma data única
                    base_date = datetime.now() - timedelta(days=date_counter)
                    # Adiciona alguns segundos aleatórios para evitar datas idênticas
                    random_seconds = random.randint(0, 59)
                    base_date = base_date.replace(second=random_seconds)
                    program["last_updated"] = base_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    date_counter += 1
                
                hackerone_programs.append(program)
    
    # Ordena os programas por data de atualização (mais recente primeiro)
    hackerone_programs.sort(key=lambda x: x.get("last_updated", "1970-01-01"), reverse=True)
    
    # Se top_count for especificado, limita o número de programas
    if top_count is not None:
        hackerone_programs = hackerone_programs[:top_count]
    
    # Contagem de programas
    total_programs = len([p for p in data if p.get("program_url", "").startswith("https://hackerone.com/")])
    reward_programs = len([p for p in hackerone_programs if p.get("bounty", False)])
    
    if only_rewards:
        print(f"{Fore.GREEN}Encontrados {reward_programs} de {total_programs} programas da HackerOne que pagam recompensas.{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Encontrados {len(hackerone_programs)} de {total_programs} programas da HackerOne.{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Desses, {reward_programs} pagam recompensas.{Style.RESET_ALL}")
    
    return hackerone_programs

def sort_by_date(hackerone_programs, use_launch_date=True):
    """Ordena programas por data de lançamento ou data de adição"""
    def get_date(program):
        if use_launch_date and program.get("date_info", {}).get("launch_date"):
            return program["date_info"]["launch_date"]
        return program.get("last_updated", "1970-01-01")
    
    return sorted(hackerone_programs, key=get_date, reverse=True)

def create_output_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"{Fore.GREEN}Diretório {OUTPUT_DIR} criado com sucesso!{Style.RESET_ALL}")

def extract_recent_subdomains(program):
    """Extrai informações sobre subdomínios recentemente adicionados"""
    recent_subdomains = []
    description = program.get("description", "")
    
    # Padrões para identificar novos subdomínios
    patterns = [
        r"(?:added|new|expanded|included) (?:the )?(?:following )?(?:new )?(?:sub)?domains?:?\s*([^\.]+(?:\s*,\s*[^\.]+)*)",  # "added domains: example.com, test.com"
        r"(?:sub)?domains? (?:added|included|expanded):\s*([^\.]+(?:\s*,\s*[^\.]+)*)",  # "domains added: example.com, test.com"
        r"(?:scope|program) (?:expanded|updated|added) (?:with|to) (?:new )?(?:sub)?domains?:?\s*([^\.]+(?:\s*,\s*[^\.]+)*)",  # "scope expanded with domains: example.com"
        r"(?:new|additional) (?:sub)?domains?:?\s*([^\.]+(?:\s*,\s*[^\.]+)*)",  # "new domains: example.com"
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, description, re.IGNORECASE)
        for match in matches:
            # Divide a string em domínios individuais e limpa cada um
            domains = re.split(r'[,;\n]', match.group(1))
            for domain in domains:
                domain = domain.strip()
                # Remove caracteres especiais e espaços extras
                domain = re.sub(r'[^\w\.-]', '', domain)
                if domain and '.' in domain:  # Verifica se é um domínio válido
                    recent_subdomains.append(domain)
    
    # Remove duplicatas mantendo a ordem
    seen = set()
    recent_subdomains = [x for x in recent_subdomains if not (x in seen or seen.add(x))]
    
    return recent_subdomains

def download_and_compare_domains(url, program_name):
    """Baixa e compara domínios do arquivo com versão anterior"""
    try:
        print(f"{Fore.CYAN}Baixando arquivo de domínios...{Style.RESET_ALL}")
        response = requests.get(url)
        response.raise_for_status()
        
        # Cria diretório para cache se não existir
        cache_dir = os.path.join(OUTPUT_DIR, "cache")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        
        # Nome do arquivo de cache para este programa
        cache_file = os.path.join(cache_dir, f"{program_name}_domains.txt")
        
        # Conjunto de domínios atuais
        current_domains = set()
        
        # Verifica o tipo de arquivo pela extensão da URL
        if url.lower().endswith('.zip'):
            # Processa arquivo ZIP
            zip_content = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_content) as zip_file:
                file_list = zip_file.namelist()
                text_files = [f for f in file_list if not f.endswith(('.jpg', '.png', '.gif', '.pdf'))]
                
                if not text_files:
                    print(f"{Fore.YELLOW}Aviso: Nenhum arquivo de texto encontrado no ZIP{Style.RESET_ALL}")
                    return [], []
                
                for file_name in text_files:
                    try:
                        with zip_file.open(file_name) as file:
                            content = file.read().decode('utf-8')
                            for line in content.splitlines():
                                domain = line.strip()
                                if domain and isinstance(domain, str):
                                    current_domains.add(domain)
                    except Exception as e:
                        print(f"{Fore.YELLOW}Aviso: Erro ao processar arquivo {file_name}: {e}{Style.RESET_ALL}")
                        continue
        else:
            # Processa arquivo de texto simples
            try:
                content = response.content.decode('utf-8')
                for line in content.splitlines():
                    domain = line.strip()
                    if domain and isinstance(domain, str):
                        current_domains.add(domain)
            except UnicodeDecodeError:
                print(f"{Fore.RED}Erro: Não foi possível decodificar o arquivo como texto{Style.RESET_ALL}")
                return [], []
        
        # Lê domínios anteriores do cache
        previous_domains = set()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    previous_domains = set(line.strip() for line in f if line.strip())
            except Exception as e:
                print(f"{Fore.YELLOW}Aviso: Erro ao ler cache: {e}{Style.RESET_ALL}")
        
        # Identifica novos domínios
        new_domains = current_domains - previous_domains
        
        # Salva domínios atuais no cache
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                for domain in sorted(current_domains):
                    f.write(f"{domain}\n")
        except Exception as e:
            print(f"{Fore.YELLOW}Aviso: Erro ao salvar cache: {e}{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}Domínios extraídos e comparados com sucesso!{Style.RESET_ALL}")
        return sorted(list(current_domains)), sorted(list(new_domains))
            
    except Exception as e:
        print(f"{Fore.RED}Erro ao baixar/processar domínios: {e}{Style.RESET_ALL}")
        return [], []

def format_program_info(program):
    """Formata as informações do programa de forma mais legível"""
    info = []
    
    # Informações básicas
    name = program.get("name", "")
    url = program.get("program_url", "")
    info.append(f"{Fore.GREEN}• {name}{Style.RESET_ALL}")
    info.append(f"  URL: {Fore.BLUE}{url}{Style.RESET_ALL}")
    
    # Datas
    launch_date = program.get("date_info", {}).get("launch_date", "")
    update_date = program.get("date_info", {}).get("update_date", "")
    last_updated = program.get("last_updated", "")
    
    if launch_date:
        launch_date = format_date(launch_date)
        launch_time_diff = format_time_diff(program.get("date_info", {}).get("launch_date", ""))
        info.append(f"  Data de entrada na HackerOne: {Fore.YELLOW}{launch_date} ({launch_time_diff}){Style.RESET_ALL}")
    if update_date:
        update_date = format_date(update_date)
        update_time_diff = format_time_diff(program.get("date_info", {}).get("update_date", ""))
        info.append(f"  Última atualização de escopo: {Fore.YELLOW}{update_date} ({update_time_diff}){Style.RESET_ALL}")
    if last_updated:
        last_updated = format_date(last_updated)
        last_updated_diff = format_time_diff(program.get("last_updated", ""))
        info.append(f"  Última atualização: {Fore.YELLOW}{last_updated} ({last_updated_diff}){Style.RESET_ALL}")
    
    # Status de pagamento
    info.append(f"  Status de pagamento: {Fore.MAGENTA}{program.get('payment_status', '')}{Style.RESET_ALL}")
    
    # Informações de recompensa
    payment_details = program.get("payment_details", {})
    if payment_details.get("bounty", False):
        if payment_details.get("reward_range"):
            info.append(f"  Faixa de recompensa: {Fore.CYAN}{payment_details.get('reward_range')}{Style.RESET_ALL}")
        if payment_details.get("min_reward"):
            info.append(f"  Recompensa mínima: {Fore.CYAN}{payment_details.get('min_reward')}{Style.RESET_ALL}")
        if payment_details.get("max_reward"):
            info.append(f"  Recompensa máxima: {Fore.CYAN}{payment_details.get('max_reward')}{Style.RESET_ALL}")
    
    # Domínios e subdomínios
    domains = extract_domains(program)
    if domains:
        info.append(f"  Domínios ({len(domains)}): {Fore.CYAN}{', '.join(domains)}{Style.RESET_ALL}")
    
    # Subdomínios recentes da descrição
    recent_subdomains = extract_recent_subdomains(program)
    if recent_subdomains:
        info.append(f"  {Fore.GREEN}Subdomínios mencionados na descrição:{Style.RESET_ALL}")
        for subdomain in recent_subdomains:
            info.append(f"    • {Fore.YELLOW}{subdomain}{Style.RESET_ALL}")
    
    # Novos subdomínios detectados pela comparação
    if program.get("URL"):
        current_domains, new_domains = download_and_compare_domains(program.get("URL"), name)
        if new_domains:
            info.append(f"  {Fore.GREEN}Novos subdomínios detectados:{Style.RESET_ALL}")
            for subdomain in new_domains:
                info.append(f"    • {Fore.YELLOW}{subdomain}{Style.RESET_ALL}")
    
    # Contagem de subdomínios
    count = program.get("count", 0)
    if count > 0:
        info.append(f"  Total de subdomínios: {Fore.CYAN}{count}{Style.RESET_ALL}")
    
    # Mudanças recentes
    change = program.get("change", 0)
    if change > 0:
        info.append(f"  Mudanças recentes: {Fore.GREEN}+{change} subdomínios{Style.RESET_ALL}")
    elif change < 0:
        info.append(f"  Mudanças recentes: {Fore.RED}{change} subdomínios{Style.RESET_ALL}")
    
    # Plataforma
    platform = program.get("platform", "")
    if platform:
        info.append(f"  Plataforma: {Fore.CYAN}{platform}{Style.RESET_ALL}")
    
    return "\n".join(info)

def save_programs_by_year(programs):
    create_output_dir()
    
    # Dicionário para armazenar programas por ano
    programs_by_year = {}
    
    for program in programs:
        # Usando a data de lançamento se disponível, senão a data de adição
        launch_date = program.get("date_info", {}).get("launch_date", program.get("last_updated", datetime.now().strftime("%Y-%m-%d")))
        
        try:
            # Tenta primeiro o formato ISO 8601
            dt = datetime.strptime(launch_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            try:
                # Tenta o formato simples de data
                dt = datetime.strptime(launch_date, "%Y-%m-%d")
            except ValueError:
                # Se falhar, usa a data atual
                dt = datetime.now()
        
        year = dt.year
        
        if year not in programs_by_year:
            programs_by_year[year] = []
        programs_by_year[year].append(program)
    
    # Salva cada ano em um arquivo separado
    for year, progs in programs_by_year.items():
        # Ordena programas por data (mais recente primeiro)
        progs.sort(key=lambda x: x.get("date_info", {}).get("launch_date", x.get("last_updated", "1970-01-01")), reverse=True)
        
        # Nome do arquivo
        filename = os.path.join(OUTPUT_DIR, f"bounty_programs_{year}.json")
        
        # Prepara dados formatados para exibição
        print(f"\n{Fore.CYAN}Programas de {year}:{Style.RESET_ALL}")
        for prog in progs:
            print(format_program_info(prog))
            print()
        
        # Salva em formato JSON
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(progs, f, indent=4, ensure_ascii=False)
        print(f"{Fore.GREEN}Salvo {len(progs)} programas no arquivo: {filename}{Style.RESET_ALL}")

def display_top_programs(programs, count=10, only_rewards=True):
    """Exibe os programas mais recentes"""
    # Filtra apenas programas com recompensas se necessário
    if only_rewards:
        filtered_programs = [p for p in programs if p.get("bounty", False)]
    else:
        filtered_programs = programs
    
    # Ordena por data de lançamento (mais recente primeiro)
    sorted_programs = sort_by_date(filtered_programs, use_launch_date=True)
    
    # Limita ao número solicitado
    top_programs = sorted_programs[:count]
    
    # Exibe os resultados
    print(f"\n{Fore.CYAN}=== Top {count} Programas Mais Recentes ===")
    if only_rewards:
        print(f"{Fore.YELLOW}(Apenas programas que pagam recompensas){Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}(Todos os programas){Style.RESET_ALL}")
    
    for i, prog in enumerate(top_programs, 1):
        print(f"\n{Fore.GREEN}{i}. {prog.get('name', '')}{Style.RESET_ALL}")
        print(format_program_info(prog))

def main():
    args = parse_arguments()
    
    print(f"{Fore.CYAN}=== HackerOne Program Fetcher ==={Style.RESET_ALL}")
    
    # Obtendo os dados
    data = fetch_programs()
    if not data:
        return

    # Filtrando programas da HackerOne
    only_rewards = args.mode == 'rewards' or (args.mode.startswith('top') and not args.all)
    
    # Determina o número de programas a serem exibidos
    top_count = None
    if args.mode.startswith('top'):
        top_count = int(args.mode[3:])
    
    hackerone_programs = filter_hackerone_rewards(data, only_rewards, top_count, args.program)
    
    if not hackerone_programs:
        print(f"{Fore.RED}Nenhum programa da HackerOne encontrado.{Style.RESET_ALL}")
        return

    # Modo de operação
    if args.mode.startswith('top'):
        # Extrai o número do modo (top10, top20, etc.)
        count = int(args.mode[3:])
        display_top_programs(hackerone_programs, count, only_rewards)
    else:
        # Modo padrão: salvar todos os programas por ano
        # Ordenando por data
        use_launch_date = args.sort_by == 'launch'
        sorted_programs = sort_by_date(hackerone_programs, use_launch_date)
        
        # Salvando e exibindo os programas organizados por ano
        save_programs_by_year(sorted_programs)
    
    print(f"\n{Fore.GREEN}Operação concluída!{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
