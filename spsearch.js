const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
// Allow all CORS requests
app.use(cors());

const PORT = process.env.PORT || 3000;

const client_id = '414df719f85e45c9bd0ee5e83d08b501';
const client_secret = 'fa7e159a0b904b8b8505bf59b6458d3a';

const getAccessToken = async () => {
  const tokenUrl = 'https://accounts.spotify.com/api/token';
  const authOptions = {
    headers: {
      'Authorization': 'Basic ' + Buffer.from(client_id + ':' + client_secret).toString('base64'),
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    data: 'grant_type=client_credentials'
  };
  const response = await axios.post(tokenUrl, authOptions.data, { headers: authOptions.headers });
  return response.data.access_token;
};

const searchSongs = async (accessToken, query, limit = 30, offset = 0) => {
  const searchUrl = 'https://api.spotify.com/v1/search';
  const options = {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    },
    params: {
      q: query,
      type: 'track',
      limit,
      offset
    }
  }; 
  const response = await axios.get(searchUrl, options);
  return response.data;
};

const getAlbumDetails = async (accessToken, albumId) => {
  const albumDetailsUrl = `https://api.spotify.com/v1/albums/${albumId}`;
  const response = await axios.get(albumDetailsUrl, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  const albumInfo = response.data;
  const tracks = albumInfo.tracks.items.map((track, index) => ({
    trackNumber: index + 1,
    trackName: track.name,
    artist: track.artists.map(artist => artist.name).join(', '),
    durationMs: track.duration_ms,
    previewUrl: track.preview_url,
    spotifyUrl: track.external_urls.spotify
  }));
  return {
    albumName: albumInfo.name,
    artist: albumInfo.artists.map(artist => artist.name).join(', '),
    releaseDate: albumInfo.release_date,
    imageUrl: albumInfo.images[0].url,
    totalTracks: albumInfo.total_tracks,
    tracks
  };
};

const getPlaylistDetails = async (accessToken, playlistId) => {
  const playlistDetailsUrl = `https://api.spotify.com/v1/playlists/${playlistId}`;
  const response = await axios.get(playlistDetailsUrl, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  const playlistInfo = response.data;
  const tracks = playlistInfo.tracks.items.map((item, index) => ({
    trackNumber: index + 1,
    trackName: item.track.name,
    artist: item.track.artists.map(artist => artist.name).join(', '),
    album: item.track.album.name,
    durationMs: item.track.duration_ms,
    previewUrl: item.track.preview_url,
    spotifyUrl: item.track.external_urls.spotify
  }));
  return {
    playlistName: playlistInfo.name,
    description: playlistInfo.description,
    owner: playlistInfo.owner.display_name,
    imageUrl: playlistInfo.images[0].url,
    totalTracks: playlistInfo.tracks.total,
    tracks
  };
};

const handleTrackDownload = async (trackUrl) => {
  const downloadUrl = `https://song-teleservice.vercel.app/spotify/down?url=${trackUrl}`;
  const response = await axios.get(downloadUrl);
  return response.data;
};

app.get('/spotify/search', async (req, res) => {
  const query = req.query.q;
  const spotifyUrl = req.query.url;
  const limit = parseInt(req.query.limit, 10) || 30;
  const offset = parseInt(req.query.offset, 10) || 0;
  
  try {
    if (spotifyUrl) {
      const isAlbum = spotifyUrl.includes('/album/');
      const isPlaylist = spotifyUrl.includes('/playlist/');
      const isTrack = spotifyUrl.includes('/track/');
      const accessToken = await getAccessToken();
      
      if (isPlaylist) {
        const playlistId = spotifyUrl.split('/').pop().split('?')[0];
        const playlistDetails = await getPlaylistDetails(accessToken, playlistId);
        return res.status(200).json({
          data: playlistDetails,
          developerCredit: 'https://t.me/Teleservices_Api'
        });
      } else if (isAlbum) {
        const albumId = spotifyUrl.split('/').pop().split('?')[0];
        const albumDetails = await getAlbumDetails(accessToken, albumId);
        return res.status(200).json({
          tracks: albumDetails.tracks,
          developerCredit: 'https://t.me/Teleservices_Api'
        });
      } else if (isTrack) {
        const trackResponse = await handleTrackDownload(spotifyUrl);
        return res.status(200).send(trackResponse);
      } else {
        return res.status(400).json({ error: 'Invalid Spotify URL' });
      }
    } else if (query) {
      const accessToken = await getAccessToken();
      if (limit > 50) {
        const firstLimit = 50;
        const secondLimit = limit - 50;
        const firstOffset = offset;
        const secondOffset = offset + 50;
        const firstPageResults = await searchSongs(accessToken, query, firstLimit, firstOffset);
        const firstTracks = firstPageResults.tracks.items;
        const secondPageResults = await searchSongs(accessToken, query, secondLimit, secondOffset);
        const secondTracks = secondPageResults.tracks.items;
        const combinedTracks = [...firstTracks, ...secondTracks];
        const trackDetailsList = combinedTracks.map((track, index) => {
          const previewUrl = track.preview_url || 'No preview available';
          const image = track.album.images.length > 0 ? track.album.images[0].url : 'No image available';
          const artists = track.artists.map(artist => ({
              name: artist.name,
              spotifyUrl: artist.external_urls.spotify,
              id: artist.id,
              uri: artist.uri
            }));
            const duration = new Date(track.duration_ms).toISOString().substr(14, 5);
            return {
              id: index + 1,
              trackName: track.name,
              artists,
              artist: track.artists.map(artist => artist.name).join(', '),
              album: track.album.name,
              albumType: track.album.album_type,
              albumExternalUrl: track.album.external_urls.spotify,
              releaseDate: track.album.release_date,
              spotifyUrl: track.external_urls.spotify,
              previewUrl,
              image,
              duration,
              popularity: track.popularity,
              explicit: track.explicit,
              trackUri: track.uri,
              durationMs: track.duration_ms,
              totalTracksInAlbum: track.album.total_tracks
            };
        });
        return res.status(200).json({
          tracks: trackDetailsList,
          developerCredit: 'https://t.me/Teleservices_Api'
        });
      } else {
        const searchResults = await searchSongs(accessToken, query, limit, offset);
        const tracks = searchResults.tracks.items;
        if (tracks.length > 0) {
          const trackDetailsList = tracks.map((track, index) => {
            const previewUrl = track.preview_url || 'No preview available';
            const image = track.album.images.length > 0 ? track.album.images[0].url : 'No image available';
            const artists = track.artists.map(artist => ({
              name: artist.name,
              spotifyUrl: artist.external_urls.spotify,
              id: artist.id,
              uri: artist.uri
            }));
            const duration = new Date(track.duration_ms).toISOString().substr(14, 5);
            return {
              id: index + 1,
              trackName: track.name,
              artists,
              artist: track.artists.map(artist => artist.name).join(', '),
              album: track.album.name,
              albumType: track.album.album_type,
              albumExternalUrl: track.album.external_urls.spotify,
              releaseDate: track.album.release_date,
              spotifyUrl: track.external_urls.spotify,
              previewUrl,
              image,
              duration,
              popularity: track.popularity,
              explicit: track.explicit,
              trackUri: track.uri,
              durationMs: track.duration_ms,
              totalTracksInAlbum: track.album.total_tracks
            };
          });
          return res.status(200).json({
            tracks: trackDetailsList,
            developerCredit: 'https://t.me/Teleservices_Api'
          });
        } else {
          return res.status(404).json({ error: 'No tracks found' });
        }
      }
    } else {
      return res.status(400).json({ error: 'Missing query parameter (q) or Spotify URL (url)' });
    }
  } catch (error) {
    console.error('Error:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
});

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
