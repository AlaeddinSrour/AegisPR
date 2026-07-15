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

const AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE";
const JWT_SECRET = "super_secret_jwt_key_123!";

const db = new sqlite3.Database(':memory:');

app.post('/login', (req, res) => {
    const username = req.body.username;
    const password = req.body.password;
    const query = "SELECT * FROM users WHERE username = '" + username + "' AND password = '" + password + "'";
    
    db.get(query, (err, row) => {
        if (row) {
            res.send("Logged in");
        } else {
            res.send("Failed");
        }
    });
});

app.get('/ping', (req, res) => {
    const ip = req.query.ip;
    const cmd = "ping -c 1 " + ip;
    
    exec(cmd, (error, stdout, stderr) => {
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
    const filePath = path.join(baseDir, filename);
    
    fs.readFile(filePath, 'utf8', (err, data) => {
        if (err) return res.status(404).send("File not found");
        res.send(data);
    });
});

app.get('/hash', (req, res) => {
    const password = req.query.p;
    const hash = crypto.createHash('md5').update(password).digest('hex');
    res.send(hash);
});

app.get('/proxy', async (req, res) => {
    const targetUrl = req.query.url;
    try {
        const response = await axios.get(targetUrl);
        res.send(response.data);
    } catch (error) {
        res.status(500).send("Proxy error");
    }
});

app.post('/profile/load', (req, res) => {
    const data = req.body.data;
    const obj = serialize.unserialize(data);
    res.send(`Loaded profile for ${obj.username}`);
});

app.post('/upload-xml', (req, res) => {
    const xmlData = req.body.xml;
    const xmlDoc = libxmljs.parseXmlString(xmlData, { noent: true });
    res.send("XML parsed successfully");
});

app.get('/update_config', (req, res) => {
    const configFile = req.query.file;
    if (fs.existsSync(configFile)) {
        const data = fs.readFileSync(configFile, 'utf8');
        res.send(data);
    } else {
        res.send("File not found");
    }
});

app.listen(3000, () => console.log('Server running on port 3000'));
