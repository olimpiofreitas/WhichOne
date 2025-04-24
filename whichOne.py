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

def download_and_compare_domains(url, program_name):
    """Baixa e compara domínios do arquivo com versão anterior"""
    try:
        print(f"{Fore.CYAN}Baixando arquivo de domínios para {program_name}...{Style.RESET_ALL}")
        response = requests.get(url, timeout=30)
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
        
        # Identifica novos domínios e domínios removidos
        new_domains = current_domains - previous_domains
        removed_domains = previous_domains - current_domains
        
        # Salva domínios atuais no cache
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                for domain in sorted(current_domains):
                    f.write(f"{domain}\n")
        except Exception as e:
            print(f"{Fore.YELLOW}Aviso: Erro ao salvar cache: {e}{Style.RESET_ALL}")
        
        # Cria um arquivo de log com as mudanças
        log_file = os.path.join(cache_dir, f"{program_name}_changes.log")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n=== Mudanças em {timestamp} ===\n")
                if new_domains:
                    f.write("\nNovos domínios:\n")
                    for domain in sorted(new_domains):
                        f.write(f"+ {domain}\n")
                if removed_domains:
                    f.write("\nDomínios removidos:\n")
                    for domain in sorted(removed_domains):
                        f.write(f"- {domain}\n")
                f.write(f"\nTotal atual: {len(current_domains)} domínios\n")
                f.write("="*50 + "\n")
        except Exception as e:
            print(f"{Fore.YELLOW}Aviso: Erro ao salvar log de mudanças: {e}{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}Domínios extraídos e comparados com sucesso!{Style.RESET_ALL}")
        print(f"- Total de domínios: {len(current_domains)}")
        print(f"- Novos domínios: {len(new_domains)}")
        print(f"- Domínios removidos: {len(removed_domains)}")
        
        return sorted(list(current_domains)), sorted(list(new_domains)), sorted(list(removed_domains))
            
    except Exception as e:
        print(f"{Fore.RED}Erro ao baixar/processar domínios: {e}{Style.RESET_ALL}")
        return [], [], []

def download_and_extract_domains(url):
    """Baixa e extrai domínios do arquivo"""
    try:
        print(f"{Fore.CYAN}Baixando arquivo de domínios...{Style.RESET_ALL}")
        response = requests.get(url, timeout=30)  # Adiciona timeout
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
                            # Tenta diferentes codificações
                            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
                            content = None
                            for encoding in encodings:
                                try:
                                    content = file.read().decode(encoding)
                                    break
                                except UnicodeDecodeError:
                                    continue
                            
                            if content is None:
                                print(f"{Fore.YELLOW}Aviso: Não foi possível decodificar o arquivo {file_name}{Style.RESET_ALL}")
                                continue
                            
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
                # Tenta diferentes codificações
                encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
                content = None
                for encoding in encodings:
                    try:
                        content = response.content.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if content is None:
                    print(f"{Fore.RED}Erro: Não foi possível decodificar o arquivo como texto{Style.RESET_ALL}")
                    return []
                
                domains = set()
                for line in content.splitlines():
                    domain = line.strip()
                    if domain and isinstance(domain, str):
                        domains.add(domain)
                print(f"{Fore.GREEN}Domínios extraídos com sucesso!{Style.RESET_ALL}")
                return sorted(list(domains))
            except Exception as e:
                print(f"{Fore.RED}Erro ao processar arquivo de texto: {e}{Style.RESET_ALL}")
                return []
            
    except requests.exceptions.Timeout:
        print(f"{Fore.RED}Erro: Tempo limite excedido ao baixar o arquivo{Style.RESET_ALL}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}Erro ao baixar arquivo: {e}{Style.RESET_ALL}")
        return []
    except Exception as e:
        print(f"{Fore.RED}Erro inesperado: {e}{Style.RESET_ALL}")
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
        response = requests.get(CHAOS_URL, timeout=30)  # Adiciona timeout
        response.raise_for_status()
        
        # Tenta decodificar o JSON com diferentes codificações
        try:
            data = response.json()
            print(f"{Fore.GREEN}Dados obtidos com sucesso da URL: {CHAOS_URL}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Total de programas encontrados: {len(data)}{Style.RESET_ALL}")
            
            # Verifica a estrutura dos dados
            if not isinstance(data, list):
                print(f"{Fore.RED}Erro: Formato de dados inválido. Esperado uma lista.{Style.RESET_ALL}")
                return None
                
            # Verifica se há programas da HackerOne
            hackerone_count = len([p for p in data if p.get("program_url", "").startswith("https://hackerone.com/")])
            print(f"{Fore.CYAN}Programas da HackerOne encontrados: {hackerone_count}{Style.RESET_ALL}")
            
        except json.JSONDecodeError:
            # Se falhar, tenta decodificar manualmente
            try:
                content = response.content.decode('utf-8')
                data = json.loads(content)
                print(f"{Fore.GREEN}Dados decodificados manualmente com sucesso.{Style.RESET_ALL}")
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"{Fore.RED}Erro ao decodificar o JSON da resposta: {e}{Style.RESET_ALL}")
                return None
        
        # Salva os dados atualizados em um arquivo de cache
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"{Fore.GREEN}Cache atualizado com sucesso.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}Aviso: Não foi possível salvar o cache: {e}{Style.RESET_ALL}")
        
        return data
    except requests.exceptions.Timeout:
        print(f"{Fore.RED}Erro: Tempo limite excedido ao buscar os dados{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}Erro ao buscar os dados: {e}{Style.RESET_ALL}")
        return None
    except Exception as e:
        print(f"{Fore.RED}Erro inesperado: {e}{Style.RESET_ALL}")
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
    parser.add_argument('-scope', type=str,
                        help='Exibir todos os domínios do escopo de um programa específico (ex: -scope airbnb)')
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
                
                # Extrai domínios e compara com versão anterior
                if program.get("URL"):
                    current_domains, new_domains, removed_domains = download_and_compare_domains(program["URL"], program["name"])
                    program["extracted_domains"] = current_domains
                    program["new_domains"] = new_domains
                    program["removed_domains"] = removed_domains
                    if new_domains or removed_domains:
                        program["last_scope_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    program["extracted_domains"] = extract_domains(program)
                    program["new_domains"] = []
                    program["removed_domains"] = []
                
                # Corrige o problema de datas iguais
                if not program.get("last_updated") or program.get("last_updated") == "1970-01-01":
                    base_date = datetime.now() - timedelta(days=date_counter)
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
    
    print(f"{Fore.CYAN}Detalhes da filtragem:{Style.RESET_ALL}")
    print(f"- Total de programas na fonte: {len(data)}")
    print(f"- Programas da HackerOne: {total_programs}")
    print(f"- Programas com recompensas: {reward_programs}")
    print(f"- Programas filtrados: {len(hackerone_programs)}")
    
    if only_rewards:
        print(f"{Fore.GREEN}Encontrados {reward_programs} de {total_programs} programas da HackerOne que pagam recompensas.{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Encontrados {len(hackerone_programs)} de {total_programs} programas da HackerOne.{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Desses, {reward_programs} pagam recompensas.{Style.RESET_ALL}")
    
    return hackerone_programs

def format_program_info(program):
    """Formata as informações do programa para exibição"""
    name = program.get("name", "Nome não disponível")
    url = program.get("program_url", "URL não disponível")
    payment_status = program.get("payment_status", "Status não disponível")
    payment_details = program.get("payment_details", {})
    date_info = program.get("date_info", {})
    new_domains = program.get("new_domains", [])
    removed_domains = program.get("removed_domains", [])
    last_scope_update = program.get("last_scope_update", "")
    is_new = program.get("is_new", False)
    
    # Extrai a plataforma da URL
    platform = "Desconhecida"
    if url.startswith("https://hackerone.com/"):
        platform = "HackerOne"
    elif url.startswith("https://bugcrowd.com/"):
        platform = "Bugcrowd"
    elif url.startswith("https://www.yeswehack.com/"):
        platform = "YesWeHack"
    elif url.startswith("https://www.intigriti.com/"):
        platform = "Intigriti"
    elif url.startswith("https://www.openbugbounty.org/"):
        platform = "OpenBugBounty"
    
    # Formata a informação de recompensa
    reward_info = ""
    if payment_details.get("reward_range"):
        reward_info = f"Recompensa: {payment_details['reward_range']}"
    
    # Formata a data de atualização
    update_date = date_info.get("update_date", "Data não disponível")
    
    # Adiciona informação sobre novos domínios
    domains_info = ""
    if new_domains or removed_domains:
        domains_info = f"\n{Fore.CYAN}Mudanças no escopo:{Style.RESET_ALL}"
        if new_domains:
            domains_info += f"\n{Fore.GREEN}Novos domínios adicionados ({len(new_domains)}):{Style.RESET_ALL}"
            for domain in new_domains[:5]:  # Mostra apenas os 5 primeiros
                domains_info += f"\n  + {domain}"
            if len(new_domains) > 5:
                domains_info += f"\n  ... e mais {len(new_domains) - 5} domínios"
        
        if removed_domains:
            domains_info += f"\n{Fore.RED}Domínios removidos ({len(removed_domains)}):{Style.RESET_ALL}"
            for domain in removed_domains[:5]:  # Mostra apenas os 5 primeiros
                domains_info += f"\n  - {domain}"
            if len(removed_domains) > 5:
                domains_info += f"\n  ... e mais {len(removed_domains) - 5} domínios"
    
    # Adiciona informação sobre programa novo
    new_program_info = ""
    if is_new:
        new_program_info = f"{Fore.GREEN}Programa recém adicionado!{Style.RESET_ALL}\n"
    
    # Monta a string formatada
    formatted_info = f"""
{new_program_info}{Fore.CYAN}Programa:{Style.RESET_ALL} {name}
{Fore.CYAN}Plataforma:{Style.RESET_ALL} {platform}
{Fore.CYAN}URL:{Style.RESET_ALL} {url}
{Fore.CYAN}Status:{Style.RESET_ALL} {payment_status}
{Fore.CYAN}{reward_info}{Style.RESET_ALL}
{Fore.CYAN}Última Atualização:{Style.RESET_ALL} {update_date}
{domains_info}"""
    return formatted_info

def sort_by_date(hackerone_programs, use_launch_date=True):
    """Ordena programas por data de lançamento ou data de adição"""
    def get_date(program):
        try:
            if use_launch_date and program.get("date_info", {}).get("launch_date"):
                date_str = program["date_info"]["launch_date"]
                try:
                    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    try:
                        return datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        pass
            return datetime.strptime(program.get("last_updated", "1970-01-01"), "%Y-%m-%dT%H:%M:%S.%fZ")
        except (ValueError, TypeError):
            return datetime.strptime("1970-01-01", "%Y-%m-%d")
    
    return sorted(hackerone_programs, key=get_date, reverse=True)

def create_output_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"{Fore.GREEN}Diretório {OUTPUT_DIR} criado com sucesso!{Style.RESET_ALL}")

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

def display_program_scope(program_name, data):
    """Exibe todos os domínios do escopo de um programa específico"""
    print(f"{Fore.CYAN}🔍 Buscando escopo do programa: {Fore.YELLOW}{program_name}{Style.RESET_ALL}")
    
    # Procura o programa
    target_program = None
    for program in data:
        if program_name.lower() in program.get("name", "").lower():
            target_program = program
            break
    
    if not target_program:
        print(f"{Fore.RED}❌ Programa '{program_name}' não encontrado.{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════════════════════════")
    print(f"{Fore.CYAN}📋 Programa: {Fore.YELLOW}{target_program['name']}")
    print(f"{Fore.CYAN}🔗 URL: {Fore.YELLOW}{target_program.get('program_url', 'Não disponível')}")
    print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════════════════════════{Style.RESET_ALL}")
    
    # Obtém os domínios
    if target_program.get("URL"):
        current_domains, _, _ = download_and_compare_domains(target_program["URL"], target_program["name"])
    else:
        current_domains = extract_domains(target_program)
    
    if not current_domains:
        print(f"{Fore.YELLOW}⚠️ Nenhum domínio encontrado no escopo.{Style.RESET_ALL}")
        return
    
    # Limpa domínios duplicados e www
    cleaned_domains = set()
    for domain in current_domains:
        # Remove www duplicado
        if domain.startswith('www.www.'):
            domain = domain[4:]  # Remove o primeiro 'www.'
        cleaned_domains.add(domain)
    
    # Separa domínios com wildcard
    wildcard_domains = []
    regular_domains = []
    
    for domain in sorted(cleaned_domains):
        if '*' in domain:
            wildcard_domains.append(domain)
        else:
            regular_domains.append(domain)
    
    # Exibe estatísticas
    print(f"\n{Fore.CYAN}📊 Estatísticas do Escopo:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}├─ Total de domínios: {Fore.YELLOW}{len(cleaned_domains)}")
    print(f"{Fore.CYAN}├─ Domínios com wildcard: {Fore.YELLOW}{len(wildcard_domains)}")
    print(f"{Fore.CYAN}└─ Domínios regulares: {Fore.YELLOW}{len(regular_domains)}{Style.RESET_ALL}")
    
    # Exibe domínios com wildcard
    if wildcard_domains:
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════════════════════════")
        print(f"{Fore.CYAN}🌟 Domínios com Wildcard ({len(wildcard_domains)}):{Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════════════════════════")
        for domain in wildcard_domains:
            print(f"{Fore.YELLOW}  * {domain}{Style.RESET_ALL}")
    
    # Exibe domínios regulares
    if regular_domains:
        print(f"\n{Fore.CYAN}═══════════════════════════════════════════════════════════════════════════════")
        print(f"{Fore.CYAN}🌐 Domínios Regulares ({len(regular_domains)}):{Style.RESET_ALL}")
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════════════════════════════════")
        for domain in regular_domains:
            print(f"{Fore.YELLOW}    {domain}{Style.RESET_ALL}")
    
    # Salva o escopo em arquivos separados
    try:
        # Salva domínios regulares
        scope_file = os.path.join(OUTPUT_DIR, f"{target_program['name']}_scope.txt")
        with open(scope_file, 'w', encoding='utf-8') as f:
            f.write(f"=== Escopo do Programa: {target_program['name']} ===\n")
            f.write(f"URL: {target_program.get('program_url', 'Não disponível')}\n")
            f.write(f"\n=== Domínios Regulares ===\n")
            for domain in regular_domains:
                f.write(f"{domain}\n")
        print(f"\n{Fore.CYAN}💾 Escopo regular salvo em: {Fore.YELLOW}{scope_file}{Style.RESET_ALL}")
        
        # Salva domínios com wildcard em arquivo separado
        if wildcard_domains:
            wildcard_file = os.path.join(OUTPUT_DIR, f"{target_program['name']}_wildcard.txt")
            with open(wildcard_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Wildcards do Programa: {target_program['name']} ===\n")
                f.write(f"URL: {target_program.get('program_url', 'Não disponível')}\n")
                f.write(f"\n=== Domínios com Wildcard ===\n")
                for domain in wildcard_domains:
                    f.write(f"{domain}\n")
            print(f"{Fore.CYAN}💾 Wildcards salvo em: {Fore.YELLOW}{wildcard_file}{Style.RESET_ALL}")
            
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️ Aviso: Erro ao salvar arquivos de escopo: {e}{Style.RESET_ALL}")

def main():
    args = parse_arguments()
    
    print(f"{Fore.CYAN}=== HackerOne Program Fetcher ==={Style.RESET_ALL}")
    
    # Obtendo os dados
    data = fetch_programs()
    if not data:
        return

    # Se o modo -scope foi especificado, exibe o escopo e sai
    if args.scope:
        display_program_scope(args.scope, data)
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
