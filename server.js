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

async function eatToAccessToken(eat) {
  try {
    const res = await axios.get('https://ff-jwt-gen-api.lovable.app/api/public/token', {
      params: { eat_token: eat },
      headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' },
      timeout: 12000,
    });
    const d = res.data;
    if (d && d.success && d.token_access) {
      return { access_token: d.token_access, note: d.note || '' };
    }
  } catch (err) {
    console.error('eatToAccessToken error:', err.message);
  }
  return null;
}

async function accessToJWT(accessToken) {
  try {
    const res = await axios.post('https://clientbp.ggblueshark.com/MajorLogin', null, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Dalvik/2.1.0',
      },
      timeout: 10000,
    });
    if (res.data && res.data.token) return res.data;
  } catch {}
  return null;
}

async function getUserInfo(accessToken) {
  try {
    const res = await axios.get('https://openid.api.garena.com/user/info', {
      params: { access_token: accessToken },
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 8000,
    });
    if (res.data) return res.data;
  } catch {}
  return null;
}

app.post('/api/verify-token', async (req, res) => {
  try {
    const { token: rawInput, action } = req.body;
    if (!rawInput || !action) {
      return res.json({ success: false, error: 'Missing token or action.' });
    }

    const isEatAction = action === 'eat_to_jwt' || action === 'eat_to_access';
    const extracted = extractToken(rawInput, isEatAction ? 'eat' : 'access');
    const tokenStr = extracted.token;

    if (!tokenStr || tokenStr.length < 10) {
      return res.json({ success: false, error: 'Invalid token format. Please paste the full URL or raw token.' });
    }

    if (action === 'eat_to_access') {
      const result = await eatToAccessToken(tokenStr);
      if (result && result.access_token) {
        const info = await getUserInfo(result.access_token);
        return res.json({
          success: true,
          token_type: 'ACCESS TOKEN',
          result_token: result.access_token,
          nickname: info?.nickname || info?.name || info?.username || 'Player',
          account_id: info?.uid || info?.account_id || info?.openid || '--',
          region: info?.region || 'GLOBAL',
        });
      }
      return res.json({
        success: false,
        error: 'Could not convert EAT to Access Token. Make sure the EAT token is valid and not expired.',
      });
    }

    if (action === 'eat_to_jwt') {
      const result = await eatToAccessToken(tokenStr);
      if (!result || !result.access_token) {
        if (tokenStr.split('.').length === 3) {
          const payload = decodeJWTPayload(tokenStr);
          if (payload) {
            return res.json({
              success: true,
              token_type: 'JWT TOKEN',
              result_token: tokenStr,
              nickname: payload.nickname || payload.name || 'Player',
              account_id: payload.sub || payload.uid || payload.account_id || '--',
              region: payload.region || 'GLOBAL',
            });
          }
        }
        return res.json({
          success: false,
          error: 'Could not exchange EAT for Access Token. The EAT may be expired or invalid.',
        });
      }

      const accessToken = result.access_token;
      const jwtResult = await accessToJWT(accessToken);
      const info = await getUserInfo(accessToken);

      if (jwtResult && jwtResult.token) {
        const payload = decodeJWTPayload(jwtResult.token);
        return res.json({
          success: true,
          token_type: 'JWT TOKEN',
          result_token: jwtResult.token,
          nickname: info?.nickname || payload?.nickname || payload?.name || 'Player',
          account_id: info?.uid || payload?.sub || payload?.account_id || '--',
          region: payload?.region || info?.region || 'GLOBAL',
        });
      }

      return res.json({
        success: true,
        token_type: 'ACCESS TOKEN',
        result_token: accessToken,
        nickname: info?.nickname || info?.name || 'Player',
        account_id: info?.uid || info?.openid || '--',
        region: info?.region || 'GLOBAL',
      });
    }

    if (action === 'access_to_jwt') {
      if (tokenStr.split('.').length === 3) {
        const payload = decodeJWTPayload(tokenStr);
        if (payload) {
          return res.json({
            success: true,
            token_type: 'JWT TOKEN',
            result_token: tokenStr,
            nickname: payload.nickname || payload.name || 'Player',
            account_id: payload.sub || payload.uid || payload.account_id || '--',
            region: payload.region || 'GLOBAL',
          });
        }
      }

      const jwtResult = await accessToJWT(tokenStr);
      const info = await getUserInfo(tokenStr);

      if (jwtResult && jwtResult.token) {
        const payload = decodeJWTPayload(jwtResult.token);
        return res.json({
          success: true,
          token_type: 'JWT TOKEN',
          result_token: jwtResult.token,
          nickname: info?.nickname || payload?.nickname || 'Player',
          account_id: info?.uid || payload?.sub || '--',
          region: payload?.region || info?.region || 'GLOBAL',
        });
      }

      if (info) {
        return res.json({
          success: true,
          token_type: 'ACCESS TOKEN (VERIFIED)',
          result_token: tokenStr,
          nickname: info.nickname || info.name || info.username || 'Player',
          account_id: info.uid || info.openid || info.account_id || '--',
          region: info.region || 'GLOBAL',
        });
      }

      return res.json({
        success: false,
        error: 'Invalid or expired Access Token. Please try again with a fresh token.',
      });
    }

    return res.json({ success: false, error: 'Unknown action.' });
  } catch (err) {
    console.error('API error:', err.message);
    return res.json({ success: false, error: 'Server error. Please try again.' });
  }
});

app.get('/api/account-info', async (req, res) => {
  try {
    const { uid } = req.query;
    if (!uid || uid.trim().length < 5) {
      return res.json({ success: false, error: 'Please enter a valid UID.' });
    }

    let data;
    try {
      const response = await axios.get('https://rizerxinfo1234.vercel.app/player-info', {
        params: { uid: uid.trim() },
        headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' },
        timeout: 15000,
        validateStatus: () => true,
      });
      data = response.data;
    } catch (err) {
      console.error('Account info fetch error:', err.message);
      if (err.code === 'ECONNABORTED' || err.message.includes('timeout')) {
        return res.json({ success: false, error: 'Request timed out. Please try again.' });
      }
      return res.json({ success: false, error: 'Could not reach the player info service.' });
    }

    if (!data || data.error) {
      const msg = (data && data.error) ? data.error : 'Player not found.';
      return res.json({ success: false, error: msg });
    }

    const basic  = data.basicInfo     || {};
    const clan   = data.clanBasicInfo || {};
    const CDN    = 'https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG';

    return res.json({
      success: true,
      player: {
        uid:         uid.trim(),
        name:        basic.nickname      || 'Unknown',
        level:       basic.level         || '--',
        exp:         basic.exp           || '--',
        rank:        basic.rankingPoints || '--',
        bp:          basic.badgePoint    || '--',
        region:      basic.region        || '--',
        guild:       clan.clanName       || 'No Guild',
        guild_level: clan.clanLevel      || '--',
        like:        basic.liked         || '--',
        avatarUrl:   basic.headPic  ? `${CDN}/${basic.headPic}.png`  : null,
        bannerUrl:   basic.bannerId ? `${CDN}/${basic.bannerId}.png` : null,
        pinUrl:      basic.pinId    ? `${CDN}/${basic.pinId}.png`    : null,
      },
    });
  } catch (err) {
    console.error('Account info error:', err.message);
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
