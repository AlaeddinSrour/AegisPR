const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const { exec } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const libxmljs = require("libxmljs");
const serialize = require('node-serialize');

const app = express();
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

const AWS_ACCESS_KEY = process.env.AWS_ACCESS_KEY;
const JWT_SECRET = process.env.JWT_SECRET;

const db = new sqlite3.Database(':memory:');

app.post('/login', (req, res) => {
    const username = req.body.username;
    const password = req.body.password;
    const query = "SELECT * FROM users WHERE username = ? AND password = ?";
    
    db.get(query, [username, password], (err, row) => {
        if (row) {
            res.send("Logged in");
        } else {
            res.send("Failed");
        }
    });
});

app.get('/ping', (req, res) => {
    const ip = req.query.ip;
    const { execFile } = require('child_process');
    execFile('ping', ['-c', '1', ip], (error, stdout, stderr) => {
        if (error) {
            res.send(`Error: ${error.message}`);
            return;
        }
        res.send(`Result: ${stdout}`);
    });
});

app.get('/download', (req, res) => {
    const filename = req.query.file;
    const baseDir = '/var/www/uploads/';
    const filePath = path.resolve(baseDir, filename);
    if (!filePath.startsWith(baseDir)) return res.status(403).send("Access Denied");
    fs.readFile(filePath, 'utf8', (err, data) => {
        if (err) return res.status(404).send("File not found");
        res.send(data);
    });
});

app.get('/hash', (req, res) => {
    const password = req.query.p;
    const hash = crypto.createHash('sha256').update(password).digest('hex');
    res.send(hash);
});

app.get('/proxy', async (req, res) => {
    const targetUrl = req.query.url;
    try {
        if (!targetUrl.startsWith('https://api.trusted.com/')) return res.status(403).send('Forbidden');
        const response = await axios.get(targetUrl);
        res.send(response.data);
    } catch (error) {
        res.status(500).send("Proxy error");
    }
});

app.post('/profile/load', (req, res) => {
    const data = req.body.data;
    const obj = JSON.parse(data);
    res.send(`Loaded profile for ${obj.username}`);
});

app.post('/upload-xml', (req, res) => {
    const xmlData = req.body.xml;
    const xmlDoc = libxmljs.parseXmlString(xmlData, { noent: false });
    res.send("XML parsed successfully");
});

app.get('/update_config', (req, res) => {
    const configFile = req.query.file;
    const baseDir = '/var/www/config/';
    const resolvedPath = path.resolve(baseDir, configFile);
    const relative = path.relative(baseDir, resolvedPath);
    if (relative.startsWith('..') || path.isAbsolute(relative)) return res.status(403).send("Access Denied");
    fs.readFile(resolvedPath, 'utf8', (err, data) => {
        if (err) return res.send("File not found");
        res.send(data);
    });
});

app.listen(3000, () => console.log('Server running on port 3000'));
