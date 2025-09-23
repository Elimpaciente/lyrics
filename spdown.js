const express = require('express');
const axios = require('axios');
const qs = require('qs');

const app = express();
const PORT = process.env.PORT || 3000;

const client_id = '414df719f85e45c9bd0ee5e83d08b501';
const client_secret = 'fa7e159a0b904b8b8505bf59b6458d3a';

const getSpotifyAccessToken = async () => {
    try {
        const response = await axios.post('https://accounts.spotify.com/api/token', 
            qs.stringify({ grant_type: 'client_credentials' }), 
            {
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    Authorization: `Basic ${Buffer.from(`${client_id}:${client_secret}`).toString('base64')}`
                }
            }
        );
        return response.data.access_token;
    } catch (error) {
        throw new Error('Error fetching Spotify access token');
    }
};

const getSpotifyTrackDetails = async (url) => {
    try {
        const response = await axios.get(`https://api.fabdl.com/spotify/get?url=${url}`);
        return response.data.result;
    } catch (error) {
        throw new Error('Error fetching Spotify track details');
    }
};

const getDownloadLink = async (gid, track_id) => {
    try {
        const response = await axios.get(`https://api.fabdl.com/spotify/mp3-convert-task/${gid}/${track_id}`);
        return response.data.result;
    } catch (error) {
        throw new Error('Error fetching download link');
    }
};

const getTrackMetadata = async (trackId, accessToken) => {
    try {
        const response = await axios.get(`https://api.spotify.com/v1/tracks/${trackId}`, {
            headers: {
                Authorization: `Bearer ${accessToken}`
            }
        });

        const track = response.data;
        return {
            id: track.id,
            title: track.name,
            artists: track.artists.map((artist) => artist.name).join(", "),
            album: track.album.name,
            releaseDate: track.album.release_date,
            duration: new Date(track.duration_ms).toISOString().substr(14, 5),
            duration_ms: track.duration_ms,
            image: track.album.images[0]?.url || "",
            spotify_url: track.external_urls.spotify,
            popularity: track.popularity,
        };
    } catch (error) {
        throw new Error('Error fetching track metadata');
    }
};

app.get('/spotify/down', async (req, res) => {
    const spotifyUrl = req.query.url;

    if (!spotifyUrl) {
        return res.status(400).json({ status: false, message: 'Spotify URL is required' });
    }

    try {
        const trackDetails = await getSpotifyTrackDetails(spotifyUrl);
        const { gid, id, name, image, artists, duration_ms } = trackDetails;
        const downloadTask = await getDownloadLink(gid, id);

        if (!downloadTask.download_url) {
            return res.status(500).json({ status: false, message: 'Failed to retrieve download link' });
        }

        const accessToken = await getSpotifyAccessToken();
        const trackMetadata = await getTrackMetadata(id, accessToken);

        const finalResult = {
            status: true,
            id,
            title: name,
            image: image,
            artist: artists,
            duration: new Date(duration_ms).toISOString().substr(14, 5),
            duration_ms,
            download_link: `https://api.fabdl.com${downloadTask.download_url}`,
            album: trackMetadata.album,
            cover: trackMetadata.image,
            isrc: trackMetadata.isrc || "N/A",
            releaseDate: trackMetadata.releaseDate,
            spotify_url: `https://open.spotify.com/track/${id}`
        };

        res.json(finalResult);

    } catch (error) {
        res.status(500).json({ status: false, message: error.message || 'An error occurred' });
    }
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});

module.exports = app;
