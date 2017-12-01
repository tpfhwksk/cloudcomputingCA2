from flask import Flask, Response, render_template, request
import json
from subprocess import Popen, PIPE
import os
from tempfile import mkdtemp
from werkzeug import secure_filename

app = Flask(__name__)


def docker(*args):
    cmd = ['docker']
    for sub in args:
        cmd.append(sub)
    process = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    if stderr.startswith('Error'):
        print 'Error: {0} -> {1}'.format(' '.join(cmd), stderr)
    return stderr + stdout

def docker_ps_to_array(output):
    all = []
    for c in [line.split() for line in output.splitlines()[1:]]:
        each = {}
        each['id'] = c[0]
        each['image'] = c[1]
        each['name'] = c[-1]
        each['ports'] = c[-2]
        all.append(each)
    return all

def docker_node_to_array(output):
    all = []
    for c in [line.split() for line in output.splitlines()[1:]]:
        each = {}
        each['id'] = c[0]
        try:
            each['manager_status'] = c[5]
            each['hostname'] = c[2]
            each['status'] = c[3]
            each['availabilty'] = c[4]
        except:
            each['hostname'] = c[1]
            each["status"] = c[2]
            each["availabilty"] = c[3]

        all.append(each)
    return all

def docker_logs_to_object(id, output):
    logs = {}
    logs['id'] = id
    all = []
    for line in output.splitlines():
        all.append(line)
    logs['logs'] = all
    return logs

def docker_images_to_array(output):
    all = []
    for c in [line.split() for line in output.splitlines()[1:]]:
        each = {}
        each['id'] = c[2]
        each['tag'] = c[1]
        each['name'] = c[0]
        all.append(each)
    return all

@app.route("/")
def index():
    return """
    Available API endpoints:
    GET /containers                     List all containers
    GET /containers?state=running      List running containers (only)
    GET /containers/<id>                Inspect a specific container
    GET /containers/<id>/logs           Dump specific container logs
    GET /images                         List all images
    POST /images                        Create a new image
    POST /containers                    Create a new container
    PATCH /containers/<id>              Change a container's state
    PATCH /images/<id>                  Change a specific image's attributes
    DELETE /containers/<id>             Delete a specific container
    DELETE /containers                  Delete all containers (including running)
    DELETE /images/<id>                 Delete a specific image
    DELETE /images                      Delete all images
    """

@app.route('/containers', methods=['GET'])
def containers_index():
    if request.args.get('state') == 'running': 
        output = docker('ps')
        resp = json.dumps(docker_ps_to_array(output))
         
    else:
        output = docker('ps', '-a')
        resp = json.dumps(docker_ps_to_array(output))

    #resp = ''
    return Response(response=resp, mimetype="application/json")

@app.route('/containers/<id>', methods=['GET'])
def containers_show(id):
    output = docker('inspect', id)

    resp = json.dumps(json.loads(output))

    return Response(response=resp, mimetype="application/json")

@app.route('/containers', methods=['POST'])
def containers_create():
    """
    Create container (from existing image using id or name)

    curl -X POST -H 'Content-Type: application/json' http://localhost:8080/containers -d '{"image": "my-app"}'
    curl -X POST -H 'Content-Type: application/json' http://localhost:8080/containers -d '{"image": "b14752a6590e"}'
    curl -X POST -H 'Content-Type: application/json' http://localhost:8080/containers -d '{"image": "b14752a6590e","publish":"8081:22"}'

    """
    body = request.get_json(force=True)
    image = body['image']
    args = ('run', '-d')
    id = docker(*(args + (image,)))[0:12]
    return Response(response='{"id": "%s"}' % id, mimetype="application/json")

@app.route('/containers/<id>', methods=['PATCH'])
def containers_update(id):
    """
    Update container attributes (support: state=running|stopped)

    curl -X PATCH -H 'Content-Type: application/json' http://localhost:8080/containers/b6cd8ea512c8 -d '{"state": "running"}'
    curl -X PATCH -H 'Content-Type: application/json' http://localhost:8080/containers/b6cd8ea512c8 -d '{"state": "stopped"}'

    """
    body = request.get_json(force=True)
    try:
        state = body['state']
        if state == 'running':
            docker('restart', id)
    except:
        pass

    resp = '{"id": "%s"}' % id
    return Response(response=resp, mimetype="application/json")

@app.route('/containers/<id>', methods=['DELETE'])
def containers_remove(id):
    """
    Delete a specific container - must be already stopped/killed

    """
    ps = docker('ps')
    containers = docker_ps_to_array(ps) 
    if len(filter(lambda a: a.get('id') == id, containers)):
        resp = 'the container %s is running' % id
    else:
        docker('rm', id)
        resp = 'the container %s is removed' % id
    return Response(response=resp, mimetype="application/json")

@app.route('/containers', methods=['DELETE'])
def containers_remove_all():
    """
    Force remove all containers - dangrous!

    """
    for cont in docker('ps', '-a', '-q').split('\n'):
        if cont:
            docker('stop', cont)
            docker('rm', cont)
    resp = 'All containers are removed'
    return Response(response=resp, mimetype="application/json")

@app.route('/containers/<id>/logs', methods=['GET'])
def containers_log(id):
    output = docker('container', 'logs', id)
    resp = json.dumps(docker_logs_to_object(id, output))
    return Response(response=resp, mimetype="application/json")

@app.route('/services', methods=['GET'])
def services_index():
    output = docker('service', 'ls')
    resp = json.dumps(docker_ps_to_array(output))
    return Response(response=resp, mimetype="application/json")

@app.route('/nodes', methods=['GET'])
def nodes_index():
    output = docker('node', 'ls')
    resp = json.dumps(docker_node_to_array(output))
    return Response(response=resp, mimetype="application/json")

@app.route('/images', methods=['GET'])
def images_index():
    output = docker('images') 
    resp = json.dumps(docker_images_to_array(output)) 
    return Response(response=resp, mimetype="application/json")

@app.route('/images', methods=['POST'])
def images_create():
    """
    Create image (from uploaded Dockerfile)

    curl -H 'Accept: application/json' -F file=@Dockerfile http://localhost:8080/images

    """
    body = request.get_json(force=True)
    dockerfile = body['file']

    docker('build', dockerfile)
    
    resp = 'the image built'
    return Response(response=resp, mimetype="application/json")

# docker image tag d8bcf085ca53 test3:0.1
@app.route('/images/<id>', methods=['PATCH'])
def images_update(id):
    """
    Update image attributes (support: name[:tag])  tag name should be lowercase only

    curl -s -X PATCH -H 'Content-Type: application/json' http://localhost:8080/images/7f2619ed1768 -d '{"tag": "test:1.0"}'

    """
    body = request.get_json(force=True)
    name = body['tag']
    docker('image', 'tag', id, name)
    resp = 'the image updated'
    return Response(response=resp, mimetype="application/json")

@app.route('/images/<id>', methods=['DELETE'])
def images_remove(id):
    """
    Delete a specific image
    """
    docker ('rmi', id)
    resp = '{"id": "%s"}' % id
    return Response(response=resp, mimetype="application/json")


@app.route('/images', methods=['DELETE'])
def images_remove_all():
    """
    Force remove all images - dangrous!

    """
    ids = docker('images', '-q').split('\n')

    for id in ids:
        if id:
            docker('rmi', '-f', id)
 
    resp = 'All of images are removed'
    return Response(response=resp, mimetype="application/json")
   
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
