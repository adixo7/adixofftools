const express = require('express');
const axios = require('axios');
const cors = require('cors');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

function extractToken(input, type) {
  input = input.trim();
  try {
    const url = new URL(input);
    if (type === 'eat' || type === 'auto') {
      const eat = url.searchParams.get('eat');
      if (eat) return { token: eat, found: 'eat' };
    }
    if (type === 'access' || type === 'auto') {
      const at = url.searchParams.get('access_token');
      if (at) return { token: at, found: 'access' };
    }
  } catch {}
  const eatMatch = input.match(/[?&]eat=([^&\s]+)/);
  if (eatMatch) return { token: eatMatch[1], found: 'eat' };
  const atMatch = input.match(/[?&]access_token=([^&\s]+)/);
  if (atMatch) return { token: atMatch[1], found: 'access' };
  return { token: input, found: type };
}

const REGIONS = [
  { id: 'IND', host: 'clientbp.ggblueshark.com', garena: 'loginod.garena.com' },
  { id: 'ID',  host: 'clientbp.ggblueshark.com', garena: 'loginsg.garena.com' },
  { id: 'SG',  host: 'clientbp.ggblueshark.com', garena: 'loginsg.garena.com' },
  { id: 'BR',  host: 'clientbp.ggblueshark.com', garena: 'loginsg.garena.com' },
  { id: 'TH',  host: 'clientbp.ggblueshark.com', garena: 'loginsg.garena.com' },
  { id: 'VN',  host: 'clientbp.ggblueshark.com', garena: 'loginsg.garena.com' },
];

async function eatToAccessToken(eat) {
  const endpoints = [
    `https://loginsg.garena.com/oauth/token/verify`,
    `https://loginod.garena.com/oauth/token/verify`,
  ];
  for (const ep of endpoints) {
    try {
      const res = await axios.post(ep, { eat }, {
        headers: { 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0' },
        timeout: 8000,
      });
      if (res.data && res.data.access_token) return res.data;
    } catch {}
  }
  try {
    const res = await axios.get(`https://openid.api.garena.com/user/info`, {
      params: { eat },
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 8000,
    });
    if (res.data && res.data.access_token) return res.data;
  } catch {}
  return null;
}

async function accessToJWT(accessToken) {
  try {
    const res = await axios.post(`https://clientbp.ggblueshark.com/MajorLogin`, null, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Dalvik/2.1.0',
      },
      timeout: 8000,
    });
    if (res.data && res.data.token) return res.data;
  } catch {}
  return null;
}

async function getUserInfoFromAccessToken(accessToken) {
  try {
    const res = await axios.get('https://openid.api.garena.com/user/info', {
      params: { access_token: accessToken },
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 8000,
    });
    return res.data;
  } catch {}
  return null;
}

function decodeJWTPayload(jwt) {
  try {
    const parts = jwt.split('.');
    if (parts.length < 2) return null;
    const payload = Buffer.from(parts[1], 'base64url').toString('utf-8');
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

app.post('/api/verify-token', async (req, res) => {
  try {
    const { token: rawInput, action } = req.body;
    if (!rawInput || !action) {
      return res.json({ success: false, error: 'Missing token or action' });
    }

    let tokenStr, tokenType;

    if (action === 'eat_to_jwt' || action === 'eat_to_access') {
      const extracted = extractToken(rawInput, 'eat');
      tokenStr = extracted.token;
      tokenType = 'eat';
    } else {
      const extracted = extractToken(rawInput, 'access');
      tokenStr = extracted.token;
      tokenType = 'access';
    }

    if (!tokenStr || tokenStr.length < 10) {
      return res.json({ success: false, error: 'Invalid token format. Please paste the full URL or token.' });
    }

    if (action === 'eat_to_access') {
      const result = await eatToAccessToken(tokenStr);
      if (result && result.access_token) {
        const info = await getUserInfoFromAccessToken(result.access_token);
        return res.json({
          success: true,
          token_type: 'ACCESS TOKEN',
          result_token: result.access_token,
          nickname: info?.nickname || info?.name || info?.username || 'Unknown',
          account_id: info?.uid || info?.account_id || info?.openid || '--',
          region: info?.region || 'GLOBAL',
        });
      }
      return res.json({ success: false, error: 'Could not convert EAT to Access Token. Make sure the EAT token is valid and not expired.' });
    }

    if (action === 'eat_to_jwt') {
      const accessResult = await eatToAccessToken(tokenStr);
      let accessToken = accessResult?.access_token;
      if (!accessToken) {
        if (tokenStr.split('.').length === 3) {
          const payload = decodeJWTPayload(tokenStr);
          if (payload) {
            return res.json({
              success: true,
              token_type: 'JWT TOKEN',
              result_token: tokenStr,
              nickname: payload.nickname || payload.name || 'Unknown',
              account_id: payload.sub || payload.uid || payload.account_id || '--',
              region: payload.region || 'GLOBAL',
            });
          }
        }
        return res.json({ success: false, error: 'Could not exchange EAT for Access Token. The EAT may be expired or invalid.' });
      }
      const jwtResult = await accessToJWT(accessToken);
      if (jwtResult && jwtResult.token) {
        const payload = decodeJWTPayload(jwtResult.token);
        const info = await getUserInfoFromAccessToken(accessToken);
        return res.json({
          success: true,
          token_type: 'JWT TOKEN',
          result_token: jwtResult.token,
          nickname: info?.nickname || payload?.nickname || payload?.name || 'Unknown',
          account_id: info?.uid || payload?.sub || payload?.account_id || '--',
          region: payload?.region || info?.region || 'GLOBAL',
        });
      }
      if (accessToken) {
        const info = await getUserInfoFromAccessToken(accessToken);
        return res.json({
          success: true,
          token_type: 'ACCESS TOKEN',
          result_token: accessToken,
          nickname: info?.nickname || info?.name || 'Unknown',
          account_id: info?.uid || info?.openid || '--',
          region: 'GLOBAL',
        });
      }
      return res.json({ success: false, error: 'Could not generate JWT. Try the EAT → Access Token action instead.' });
    }

    if (action === 'access_to_jwt') {
      if (tokenStr.split('.').length === 3) {
        const payload = decodeJWTPayload(tokenStr);
        if (payload) {
          return res.json({
            success: true,
            token_type: 'JWT TOKEN',
            result_token: tokenStr,
            nickname: payload.nickname || payload.name || 'Unknown',
            account_id: payload.sub || payload.uid || payload.account_id || '--',
            region: payload.region || 'GLOBAL',
          });
        }
      }
      const jwtResult = await accessToJWT(tokenStr);
      if (jwtResult && jwtResult.token) {
        const payload = decodeJWTPayload(jwtResult.token);
        const info = await getUserInfoFromAccessToken(tokenStr);
        return res.json({
          success: true,
          token_type: 'JWT TOKEN',
          result_token: jwtResult.token,
          nickname: info?.nickname || payload?.nickname || 'Unknown',
          account_id: info?.uid || payload?.sub || '--',
          region: payload?.region || 'GLOBAL',
        });
      }
      const info = await getUserInfoFromAccessToken(tokenStr);
      if (info) {
        return res.json({
          success: true,
          token_type: 'ACCESS TOKEN (VERIFIED)',
          result_token: tokenStr,
          nickname: info.nickname || info.name || info.username || 'Unknown',
          account_id: info.uid || info.openid || info.account_id || '--',
          region: info.region || 'GLOBAL',
        });
      }
      return res.json({ success: false, error: 'Invalid Access Token. Make sure it is not expired.' });
    }

    return res.json({ success: false, error: 'Unknown action.' });
  } catch (err) {
    console.error('API error:', err.message);
    return res.json({ success: false, error: 'Server error. Please try again.' });
  }
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const PORT = 5000;
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running on port ${PORT}`);
});
