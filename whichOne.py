def extract_platform_info(program):
    """Extrai informações sobre a plataforma de bug bounty"""
    platform_info = {
        "name": "",
        "url": "",
        "type": ""
    }
    
    # Verifica a URL do programa para identificar a plataforma
    program_url = program.get("program_url", "").lower()
    
    if "hackerone.com" in program_url:
        platform_info["name"] = "HackerOne"
        platform_info["url"] = program_url
        platform_info["type"] = "hackerone"
    elif "bugcrowd.com" in program_url:
        platform_info["name"] = "Bugcrowd"
        platform_info["url"] = program_url
        platform_info["type"] = "bugcrowd"
    elif "intigriti.com" in program_url:
        platform_info["name"] = "Intigriti"
        platform_info["url"] = program_url
        platform_info["type"] = "intigriti"
    elif "yeswehack.com" in program_url:
        platform_info["name"] = "YesWeHack"
        platform_info["url"] = program_url
        platform_info["type"] = "yeswehack"
    elif "federacy.com" in program_url:
        platform_info["name"] = "Federacy"
        platform_info["url"] = program_url
        platform_info["type"] = "federacy"
    elif "openbugbounty.org" in program_url:
        platform_info["name"] = "OpenBugBounty"
        platform_info["url"] = program_url
        platform_info["type"] = "openbugbounty"
    else:
        # Tenta extrair a plataforma da descrição
        description = program.get("description", "").lower()
        if "hackerone" in description:
            platform_info["name"] = "HackerOne"
            platform_info["type"] = "hackerone"
        elif "bugcrowd" in description:
            platform_info["name"] = "Bugcrowd"
            platform_info["type"] = "bugcrowd"
        elif "intigriti" in description:
            platform_info["name"] = "Intigriti"
            platform_info["type"] = "intigriti"
        elif "yeswehack" in description:
            platform_info["name"] = "YesWeHack"
            platform_info["type"] = "yeswehack"
        elif "federacy" in description:
            platform_info["name"] = "Federacy"
            platform_info["type"] = "federacy"
        elif "openbugbounty" in description:
            platform_info["name"] = "OpenBugBounty"
            platform_info["type"] = "openbugbounty"
        else:
            platform_info["name"] = "Desconhecida"
            platform_info["type"] = "unknown"
    
    return platform_info

def format_program_info(program):
    """Formata as informações do programa de forma mais legível"""
    info = []
    
    # Informações básicas
    name = program.get("name", "")
    url = program.get("program_url", "")
    info.append(f"{Fore.GREEN}• {name}{Style.RESET_ALL}")
    info.append(f"  URL: {Fore.BLUE}{url}{Style.RESET_ALL}")
    
    # Informações da plataforma
    platform_info = extract_platform_info(program)
    if platform_info["name"]:
        info.append(f"  Plataforma: {Fore.MAGENTA}{platform_info['name']}{Style.RESET_ALL}")
    
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
    
    return "\n".join(info) 
