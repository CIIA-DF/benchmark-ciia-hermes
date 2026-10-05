# Guia de Configuração e Deploy na VPS Hostinger

Este documento orienta o passo a passo completo para configurar o repositório e realizar o deploy do Portal Next.js e da infraestrutura na VPS Hostinger.

---

## 1. Acesso SSH e Preparação da VPS

### 1.1 Conectar via SSH
Conecte-se à sua VPS Hostinger com as credenciais SSH fornecidas no painel:
```bash
ssh root@<IP_DA_VPS_HOSTINGER>
```

### 1.2 Atualização de Pacotes e Instalação de Dependências
Execute os comandos para atualizar o sistema e instalar o **Node.js 20 LTS**, **Nginx**, **Git** e **PM2**:
```bash
# Atualizar lista de pacotes do sistema
sudo apt update && sudo apt upgrade -y

# Instalar Node.js (v20 LTS), Git e Nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs git nginx

# Instalar o PM2 globalmente (Gerenciador de Processos)
sudo npm install -g pm2
```

---

## 2. Configuração do Repositório Git na VPS

### 2.1 Clonar o Repositório
Escolha um diretório de trabalho na VPS (ex: `/var/www` ou `~/apps`):
```bash
mkdir -p /var/www
cd /var/www
git clone https://github.com/CIIA-DF/benchmark-ciia-hermes.git
cd benchmark-ciia-hermes
```

### 2.2 Trocar para a Branch Desejada
```bash
git fetch origin
git checkout team/portal  # ou main
```

---

## 3. Deploy do Portal (Next.js)

### 3.1 Instalação de Dependências e Build de Produção
```bash
cd /var/www/benchmark-ciia-hermes/portal

# Instalar dependências
npm install

# Gerar build de produção
npm run build
```

### 3.2 Executar a Aplicação com PM2
O PM2 gerencia a aplicação em background e garante reinício automático caso a VPS seja reiniciada:
```bash
# Iniciar o servidor Next.js na porta 3000
pm2 start npm --name "portal-sei" -- start -- -p 3000

# Salvar o estado do PM2 para inicialização automática no boot
pm2 save
pm2 startup
```

---

## 4. Configuração do Nginx (Proxy Reverso)

### 4.1 Criar o Arquivo de Configuração
Crie um arquivo de site no Nginx:
```bash
sudo nano /etc/nginx/sites-available/portal
```

Cole a configuração abaixo (substituindo `<IP_DA_VPS_OU_DOMINIO>` pelo seu IP da Hostinger ou domínio):
```nginx
server {
    listen 80;
    server_name <IP_DA_VPS_OU_DOMINIO>;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### 4.2 Ativar o Site e Reiniciar o Nginx
```bash
sudo ln -s /etc/nginx/sites-available/portal /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 5. Configuração de SSL / HTTPS (Opcional com Domínio)

Se você possui um domínio apontado no DNS da Hostinger para o IP da sua VPS:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d seu-dominio.com
```

---

## 6. Comandos Úteis de Manutenção e Atualização

- **Ver logs do Portal:** `pm2 logs portal-sei`
- **Status da aplicação:** `pm2 status`
- **Reiniciar a aplicação:** `pm2 restart portal-sei`
- **Atualizar o Portal após novas alterações no Git:**
  ```bash
  cd /var/www/benchmark-ciia-hermes/portal
  git pull origin team/portal
  npm install
  npm run build
  pm2 restart portal-sei
  ```
