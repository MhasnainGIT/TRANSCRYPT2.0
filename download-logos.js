const https = require('https');
const fs = require('fs');
const path = require('path');

const logos = [
  {
    url: 'https://raw.githubusercontent.com/MetaMask/brand-resources/master/SVG/metamask-fox.svg',
    filename: 'metamask-logo.svg'
  },
  {
    url: 'https://raw.githubusercontent.com/WalletConnect/walletconnect-assets/master/Logo/Blue%20(Default)/Logo%20(Blue)/logo.svg',
    filename: 'walletconnect-logo.svg'
  },
  {
    url: 'https://raw.githubusercontent.com/coinbase/coinbase-wallet-sdk/master/logo/blue.png',
    filename: 'coinbase-wallet-logo.png'
  }
];

const downloadDir = path.join(__dirname, 'Frontend', 'public', 'wallet-logos');

// Create directory if it doesn't exist
if (!fs.existsSync(downloadDir)) {
  fs.mkdirSync(downloadDir, { recursive: true });
}

// Download each logo
logos.forEach(logo => {
  const file = fs.createWriteStream(path.join(downloadDir, logo.filename));
  https.get(logo.url, response => {
    response.pipe(file);
    file.on('finish', () => {
      file.close();
      console.log(`Downloaded ${logo.filename}`);
    });
  }).on('error', err => {
    fs.unlink(path.join(downloadDir, logo.filename));
    console.error(`Error downloading ${logo.filename}:`, err.message);
  });
});
