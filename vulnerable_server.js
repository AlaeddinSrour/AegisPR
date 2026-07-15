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

// Hardcoded Secrets
const AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE";
const JWT_SECRET = "super_secret_jwt_key_123!";

const db = new sqlite3.Database(':memory:');

// 1. SQL Injection
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

// 2. Command Injection
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

// 3. Path Traversal
app.get('/download', (req, res) => {
    const filename = req.query.file;
    const baseDir = '/var/www/uploads/';
    const filePath = path.join(baseDir, filename);
    
    fs.readFile(filePath, 'utf8', (err, data) => {
        if (err) return res.status(404).send("File not found");
        res.send(data);
    });
});

// 4. Insecure Cryptographic Hashing
app.get('/hash', (req, res) => {
    const password = req.query.p;
    const hash = crypto.createHash('md5').update(password).digest('hex');
    res.send(hash);
});

// 5. Server-Side Request Forgery (SSRF)
app.get('/proxy', async (req, res) => {
    const targetUrl = req.query.url;
    try {
        const response = await axios.get(targetUrl);
        res.send(response.data);
    } catch (error) {
        res.status(500).send("Proxy error");
    }
});

// 6. Insecure Deserialization
app.post('/profile/load', (req, res) => {
    const data = req.body.data;
    // user input passed directly to unsafe node-serialize un-serialize function
    const obj = serialize.unserialize(data);
    res.send(`Loaded profile for ${obj.username}`);
});

// 7. XML External Entity (XXE)
app.post('/upload-xml', (req, res) => {
    const xmlData = req.body.xml;
    // Parsing XML with NOENT enables external entity expansion (XXE)
    const xmlDoc = libxmljs.parseXmlString(xmlData, { noent: true });
    res.send("XML parsed successfully");
});

// 8. Time-of-Check to Time-of-Use (TOCTOU)
app.get('/update_config', (req, res) => {
    const configFile = req.query.file;
    if (fs.existsSync(configFile)) {
        // Race condition: file could be replaced/symlinked between check and read
        const data = fs.readFileSync(configFile, 'utf8');
        res.send(data);
    } else {
        res.send("File not found");
    }
});

app.listen(3000, () => console.log('Server running on port 3000'));
