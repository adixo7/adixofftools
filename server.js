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

const GARENA_COOKIE_CACHE = { cookie: '', expires: 0 };
const FF_REGIONS = ['IND','SG','BR','ID','TW','VN','TH','ME','PK','CIS','BD','RU','US'];

async function getGarenaCookie() {
  if (GARENA_COOKIE_CACHE.cookie && Date.now() < GARENA_COOKIE_CACHE.expires) {
    return GARENA_COOKIE_CACHE.cookie;
  }
  try {
    const r = await axios.get('https://shop.garena.my/power-station?itemId=1300108&game=100067', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
      },
      timeout: 10000,
      validateStatus: () => true,
    });
    const raw = r.headers['set-cookie'] || [];
    const cookieStr = raw.map(c => c.split(';')[0]).join('; ');
    GARENA_COOKIE_CACHE.cookie = cookieStr;
    GARENA_COOKIE_CACHE.expires = Date.now() + 5 * 60 * 1000;
    return cookieStr;
  } catch { return ''; }
}

async function garenaLookup(uid) {
  const cookie = await getGarenaCookie();
  const r = await axios.post('https://shop.garena.my/api/auth/player_id_login',
    { app_id: 100067, login_id: uid },
    {
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://shop.garena.my',
        'Referer': 'https://shop.garena.my/power-station?itemId=1300108&game=100067',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
        'sec-ch-ua-mobile': '?1',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        ...(cookie ? { 'Cookie': cookie } : {}),
      },
      timeout: 12000,
      validateStatus: () => true,
    }
  );
  return r.data;
}

async function ffStatslookup(uid, region) {
  const r = await axios.get(`https://freefire-api-six.vercel.app/get_player_stats`, {
    params: { server: region, uid, matchmode: 'RANKED', gamemode: 'br' },
    timeout: 10000,
    validateStatus: () => true,
  });
  return r.data;
}

app.get('/api/account-info', async (req, res) => {
  try {
    const { uid, region } = req.query;
    if (!uid || uid.trim().length < 5) {
      return res.json({ success: false, error: 'Please enter a valid UID.' });
    }
    const uidStr = uid.trim();

    let nickname = null, playerRegion = null, imgUrl = null;
    let statsData = null;

    try {
      const gData = await garenaLookup(uidStr);
      if (gData && gData.nickname && !gData.url && !gData.error) {
        nickname    = gData.nickname;
        playerRegion = gData.region || null;
        imgUrl      = gData.img_url || null;
      } else if (gData && gData.url) {
        console.log('Garena CAPTCHA hit, proceeding without name');
      } else if (gData && gData.error === 'invalid_id') {
        return res.json({ success: false, error: 'UID not found. Please check and try again.' });
      }
    } catch (err) {
      console.error('Garena lookup error:', err.message);
    }

    const regionToTry = playerRegion || region || 'IND';
    const regionsToTry = [regionToTry, ...FF_REGIONS.filter(r => r !== regionToTry)];

    for (const reg of regionsToTry.slice(0, 4)) {
      try {
        const sd = await ffStatslookup(uidStr, reg);
        if (sd && sd.success) {
          statsData = sd.data;
          if (!playerRegion) playerRegion = reg;
          break;
        }
      } catch {}
    }

    if (!nickname && !statsData) {
      return res.json({ success: false, error: 'Player not found. Check the UID and try again.' });
    }

    const solo  = statsData?.solostats  || {};
    const duo   = statsData?.duostats   || {};
    const squad = statsData?.quadstats  || {};

    const totalKills  = (solo.detailedstats?.kills  || 0) + (duo.detailedstats?.kills  || 0) + (squad.detailedstats?.kills  || 0);
    const totalGames  = (solo.detailedstats?.matches || 0) + (duo.detailedstats?.matches || 0) + (squad.detailedstats?.matches || 0);
    const totalWins   = (solo.detailedstats?.wins    || 0) + (duo.detailedstats?.wins    || 0) + (squad.detailedstats?.wins   || 0);

    return res.json({
      success: true,
      player: {
        uid:        uidStr,
        name:       nickname || 'Player ' + uidStr.slice(-4),
        region:     playerRegion || '--',
        avatarUrl:  imgUrl || null,
        bannerUrl:  null,
        level:      '--',
        rank:       '--',
        bp:         '--',
        like:       '--',
        guild:      'N/A',
        kills:      totalKills  || '--',
        games:      totalGames  || '--',
        wins:       totalWins   || '--',
        kd:         totalKills && (totalGames - totalWins) > 0
                      ? (totalKills / (totalGames - totalWins)).toFixed(2)
                      : '--',
        winRate:    totalGames > 0
                      ? ((totalWins / totalGames) * 100).toFixed(1) + '%'
                      : '--',
      },
    });
  } catch (err) {
    console.error('Account info error:', err.message);
    return res.json({ success: false, error: 'Server error. Please try again.' });
  }
});

app.get('/api/guild-info', async (req, res) => {
  try {
    const { guildid, region } = req.query;
    if (!guildid || guildid.trim().length < 3) {
      return res.json({ success: false, error: 'Please enter a valid Guild ID.' });
    }
    const gidStr = guildid.trim();
    const regionToTry = region || 'IND';
    const regionsToTry = [regionToTry, ...FF_REGIONS.filter(r => r !== regionToTry)];

    let guildData = null;

    for (const reg of regionsToTry.slice(0, 5)) {
      try {
        const r = await axios.get('https://star-guild-info.lovable.app/api/public/info', {
          params: { clan_id: gidStr, region: reg },
          headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' },
          timeout: 12000,
          validateStatus: () => true,
        });
        if (r.data && r.data.status === 'success') {
          guildData = r.data;
          break;
        }
      } catch {}
    }

    if (!guildData) {
      return res.json({ success: false, error: 'Guild not found. Please check the Guild ID and try again.' });
    }

    const activityPoints = guildData.guild_activity_points || guildData.xp || 0;
    const activityDisplay = activityPoints > 0
      ? activityPoints.toLocaleString()
      : '--';

    return res.json({
      success: true,
      guild: {
        id: String(guildData.guild_id || guildData.clan_id || gidStr),
        name: guildData.clan_name || 'Unknown Guild',
        level: guildData.guild_level || guildData.level || '--',
        region: guildData.region || guildData.requested_region || '--',
        members: guildData.current_members || '--',
        totalMembers: guildData.total_members || '--',
        membersOnline: guildData.members_online || '--',
        leaderId: String(guildData.guild_leader_id || guildData.leader_id || '--'),
        activity: activityDisplay,
        rank: guildData.rank || guildData.guild_position || '--',
        score: guildData.score || guildData.glory_points || '--',
        description: guildData.guild_bio || guildData.welcome_message || '',
        avatarUrl: null,
      },
    });
  } catch (err) {
    console.error('Guild info error:', err.message);
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
