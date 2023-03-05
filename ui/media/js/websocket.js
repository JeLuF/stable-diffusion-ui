
class ConnectionManager {
    constructor(url) {
        this.url = url
        this.queue = []
        this.subscriptions = []
        this.connect()
        this.subscribe("broadcast")
        this.subscribe(SD.sessionId)
        this.handler = []
        this.sleep = ms => new Promise(r => setTimeout(r, ms));
    }


    connect() {
        this.socket = new WebSocket(this.url)
        console.log(this.socket)
        this.socket.addEventListener('open', this.bind((event) => {
            this.subscriptions.forEach( (s) => { this.subscribe(s) })
            while (this.queue.length > 0) {
                this.sendJSON(this.queue.shift())
            }
        }))
        this.socket.addEventListener('message', this.bind((event) => {
            let data = JSON.parse(event.data)
            console.log('Message from server ', data)
            if (data.type in this.handler) {
                this.handler[data.type].forEach((f) => { f(data) })
            } else { 
                console.log('No handler for ', data.type)
            }
        }, this))
        this.socket.addEventListener('error', this.bind(async function(error) {
            console.error("Websocket ERROR error", err.message)
            this.socket.close()
            // console.error(this.socket)
            // await this.sleep(2000)
            // this.connect()
        }, this))
        this.socket.addEventListener('close', this.bind(async function(event)  {
            console.warn("Websocket CLOSE event")
            await this.sleep(2000)
            this.connect()
        }, this))
    }

    sendJSON(data) {
        if (this.socket.readyState != 1) { // 1 == OPEN
            console.log('sending JSON')
            console.log(JSON.stringify(data))
            this.queue.push(data)
        } else {
            console.log('queueing JSON')
            console.log(JSON.stringify(data))
            this.socket.send(JSON.stringify(data))
        }
    }

    subscribe(channel_name) {
        if (! this.subscriptions.includes(channel_name)) {
            this.sendJSON({"type":"subscribe", "channel":channel_name})
            this.subscriptions.push(channel_name)
        }
    }

    addHandler(type, fn) {
        if ( type in this.handler ) {
            this.handler[type].push(fn)
        } else {
            this.handler[type] = [fn]
        }
    }

    // remember 'this' - http://blog.niftysnippets.org/2008/04/you-must-remember-this.html
    bind(f, obj) {
        return function() {
            return f.apply(obj, arguments)
        }
    }

}

let connection_manager = new ConnectionManager('ws://localhost:9000/ws')

connection_manager.sendJSON({'channel': 'broadcast', 'type': 'ping', 'count': 1})
