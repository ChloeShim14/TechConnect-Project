'''
File: app.py file for Tech Connect
Author: Claire Cao, Diya Khanna, Chloe Shim, Sophia Xin
Description: Main entry point for the TechConnect web application, handles the
    main functionality of the project using Flask and API endpoints.
Version: 9 December 2024
'''
from flask import (Flask, render_template, make_response, url_for, request,
                   redirect, flash, session, send_from_directory, jsonify)
from werkzeug.utils import secure_filename
import os 
import user_queries as user_db
import post_queries as post_db
import helper  #import helper.py, which contains helper functions that does repetitive conversions and such 
import pymysql

app = Flask(__name__)

# one or the other of these. Defaults to MySQL (PyMySQL)
# change comment characters to switch to SQLite

import cs304dbi as dbi
# import cs304dbi_sqlite3 as dbi

import secrets

app.secret_key = 'your secret here'
# replace that with a random key
app.secret_key = secrets.token_hex()

# This gets us better error messages for certain common request errors
app.config['TRAP_BAD_REQUEST_ERRORS'] = True

# new for file upload
app.config['PROFILE_UPLOADS'] = 'uploads/profile_pic_uploads'
app.config['POST_UPLOADS'] = 'uploads/post_uploads'

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# ==========================================================
# Helper functions called in app.py that are related to sessions
def is_logged_in():
    if 'user_id' not in session:
        flash("Session has expired or you are not logged in.")
        return False
    return True

#---------------------#
#  Welcome & Home     #
#---------------------#
@app.route('/')
def index():
    """
    Renders a welcome page for new users to sign up and returning 
    users to log in. If the user is not logged in, the welcome page is displayed.
    """
    if 'user_id' not in session:
        # If the user is not logged in, show the welcome page to prompt for login/signup
        return render_template('auth/welcome.html', page_title='Welcome Page')

    # If the user is logged in, redirect them to the home page
    return redirect(url_for('home'))

@app.route('/home/')
def home():
    """
    Renders a home page for logged in users that displays a feed with recent posts.
    (Will also display mentorship information in future versions.)
    """
    if not is_logged_in():
        return redirect(url_for('index'))
    conn = dbi.connect()

    user_id = session.get('user_id')
    user_name = post_db.get_user_name_by_uid(conn, user_id)
    num_posts = 10 #specifies number of recent posts shown

    unformatted_recent_posts = post_db.get_latest_posts(conn, num_posts) 
    recent_posts = post_db.format_posts_values(unformatted_recent_posts) #formatting

    unformatted_user_posts = post_db.get_posts_by_user(conn, user_id) 
    current_user_posts = post_db.format_posts_values(unformatted_user_posts) #formatting
    return render_template('home/index.html',
                           page_title='Home Page', 
                           posts = recent_posts,
                           current_user_posts = current_user_posts,
                           uid = user_id,
                           name = user_name)



#---------------------#
#  File Upload        #
#---------------------#

@app.route('/profile_pic/<int:user_id>')
def profile_pic(user_id):
    """
    Serves the profile picture for the given user.

    If the user is logged in and has a profile picture, the file is served from 
    the upload directory. Otherwise, returns a default profile picture file. 
    Redirects to the home page if the user is not logged in.

    Args:
        user_id (int): The ID of the user.

    Returns:
        Response or None: The profile picture file served via `send_from_directory`, 
        or None if no picture exists. Redirects if the user is not logged in.
    """
    conn = dbi.connect()
    if not is_logged_in():
        return redirect(url_for('index'))
    row = user_db.serve_profile_picture(conn,user_id) #if profile pic exists, row is a truthy value 
    if row: #if this user has profile picture, send the user's profile pic from uploads directory
        return send_from_directory(app.config['PROFILE_UPLOADS'],row['filename'])
    else: #otherwise, return a default image file
        return send_from_directory(app.config['PROFILE_UPLOADS'],'default_profile.png')


@app.route('/post_file/<int:post_id>/<filename>')
def post_file(post_id, filename):
    """
    Serves the file of a particular post

    If the user is logged in and there exists a post, the image is served from 
    the configured upload directory. If no picture is found, returns None.

    Args:
        post_id (int): The ID of the post.

    Returns: 
        Response: The post file or None if not found.
    """
    if not is_logged_in():
        return redirect(url_for('index'))
    return send_from_directory(app.config['POST_UPLOADS'], filename)


#---------------------------#
#  Signup & Login & Logout  #
#---------------------------#
@app.route('/signup/', methods=["GET", "POST"])
def signup():
    """
    Handles user sign-up process.

    GET: Displays the sign-up page for users to create a new account with 
    username and password. 

    POST: Attempts to add the new username and password to the `userpass` 
    table in the database. If the username is already taken, an error message 
    is flashed, and the user is returned to the sign-up page. 
    Assumes that Passwords do not need to be unique.
    """
    conn = dbi.connect()
    if request.method == 'GET':
        return render_template('auth/signup.html', page_title = "Sign Up Page")
    
    else:  # If method is POST
        username = request.form.get('username')
        passwd1 = request.form.get('password1')
        passwd2 = request.form.get('password2')
        if passwd1 != passwd2: #check whether the two passwords match 
            flash('Passwords do not match. Please try again!')
            return render_template('auth/signup.html', page_title = "Sign Up Page")
        try: #try inserting the new user 
            uid = user_db.insert_user(conn, username, passwd1)
            session['username'] = username
            session['user_id'] = uid
            session['logged_in'] = True
            session['visits'] = 1
            flash('Welcome! Complete your profile to get started.')
            return redirect(url_for('profile_setup'))  # Redirect to profile setup page 
        except pymysql.err.IntegrityError as err: 
            if err.args[0] == pymysql.constants.ER.DUP_ENTRY:
                flash(f"Username {username} is already taken. Please choose another one.")
            else: #some other error 
                flash("An error occurred while creating your account. Please try again.")
            return render_template('auth/signup.html', page_title = "Sign Up Page") #bring user back to the sign-up page. 

@app.route('/login/',methods = ["POST"])
def login():
    """
    Handles the login process for returning users.
    GET: Renders the login page.  
    POST: Validates the submitted username and password using a helper function.  
    - On failure: Flashes error message and bring user back to the login page.  
    - On success: Redirects the user to the home page.
    """
    conn = dbi.connect()
    #get username and password that the user entered from the login form
    username = request.form.get('username')
    password = request.form.get('password')
    result = user_db.login_user(conn,username,password) 
    if result is None:
        flash('User with this username does not exist. Please try again.')
        return redirect(url_for('index'))
    if result is False:
        # Username found, but password is incorrect
        flash('Incorrect password. Please try again.')
        return redirect(url_for('index'))
    session['user_id'] = result['uid']
    session['username'] = username
    session['logged_in'] = True
    if 'visits' in session:
        session['visits'] += 1
    else:
        session['visits'] = 1
    flash('Welcome back! Login successful.')
    return redirect(url_for('home')) 
      
@app.route('/logout/', methods = ["POST"])
def logout():
    """
    Handles user logout.
    - If the user is logged in, clears the session and redirects to the welcome page.
    - If the user is not logged in, redirects to the welcome page.
    """
    if is_logged_in(): #checks this just in case session expires 
        session.pop('username')
        session.pop('user_id')
        session.pop('logged_in')
        flash('You are logged out')
        return redirect(url_for('index')) 
    else: 
        return redirect(url_for('index'))
    


#-------------------------------#
# User Profile & Related Search #
#-------------------------------#

@app.route('/profile/<int:user_id>')
def profile(user_id):
    """
    Handles the display of a user's profile.

    Retrieves the profile data for the specified user based on `user_id`, 
    processes the data (e.g., converts `None` to 'Not Applicable' and binary 
    values to descriptive strings), and renders the profile page.

    If the session has expired or the user profile is not found, the function 
    handles the error by flashing an appropriate message and redirecting 
    the user as needed.
    """
    if not is_logged_in():
        return redirect(url_for('index')) #redirect to welcome page 
    session_uid = session['user_id'] #uid of this logged-in user 
    conn = dbi.connect()
    profile_data = user_db.get_profile(conn,user_id) #get profile data of the user by using user_id as key 
    if profile_data: #if profile_data is not None 
        profile_data = helper.convert_None_to_string(profile_data)  #Convert fields with value None to 'Not Specified' 

        if profile_data['is_interested_in_mentorship'] == 0:   #Convert boolean values (0/1) to descriptive String 
            profile_data['is_interested_in_mentorship'] = 'Not Interested'
        elif profile_data['is_interested_in_mentorship'] == 1: 
            profile_data['is_interested_in_mentorship'] = 'Interested'
        else:
            profile_data['is_interested_in_mentorship'] = 'Not Specified (Inactive User)'
        return render_template('profile/view.html',
                               page_title = "View Profile",  
                               uid = session_uid, #uid of this user who'se logged in
                               src = url_for('profile_pic', user_id = user_id),
                               profile_uid = user_id, #uid associated with the profile in question 
                               profile_data = profile_data)
    flash('User profile not found..') #flashes this if user profile not found
    return redirect(url_for('home'))


@app.route('/profile/setup/',methods=["GET","POST"]) 
def profile_setup():
    """
    Sets up a new user's profile data.
    GET: Renders the profile setup page.  
    POST: Processes form input and attempts to insert the user's data into `user` table. 
    - On success: Redirects the user to the home (feed) page.  
    - On failure (e.g., database error): Returns the user to the profile setup page.
    """
    conn = dbi.connect()
    user_id = session.get('user_id')
    if not user_id:
        flash("User not logged in.")
        return redirect(url_for('index')) # redirect to welcome page 
    if request.method == "GET": 
        return render_template('profile/setup.html', 
                                page_title = "Profile Setup", 
                                uid = user_id)
    
    else: #if method is POST
        try:
            user_data = dict(request.form) #copy of request.form
            career_interests = request.form.getlist('career_interests[]')
            career_interests_str = ', '.join(career_interests)
            user_data['career_interests'] = career_interests_str
            #convert string booleans to real Boolean values
            user_data = helper.convert_to_bool(user_data)
            #convert empty string (values not specified for optional fields) to None
            user_data = helper.convert_to_None(user_data)
            #call helper function to try to insert user's personal details to user table
            user_db.add_user_info(conn,user_id,user_data)
            #redirect to the user's profile page if profile setup is successful 
            f = request.files['pic']
            if f: #if profile pic is uploaded 
                user_filename = f.filename
                ext = user_filename.split('.')[-1]
                allowed_extensions = {'png', 'jpg', 'jpeg'}
                if ext not in allowed_extensions:
                    flash("Invalid file type. Only image files are allowed.")
                    return render_template('profile/setup.html', 
                                            page_title = "Profile Setup", 
                                            uid = user_id)
                filename = secure_filename('{}.{}'.format(user_id,ext))
                pathname = os.path.join(app.config['PROFILE_UPLOADS'],filename)
                f.save(pathname)
                user_db.upload_profile_pic(conn,user_id,filename)
            #call helper function to upload the image to table.      
            return redirect(url_for('profile',user_id=user_id))
        except Exception as err:
            flash('Error setting up profile. Please try again.')
            return render_template('profile/setup.html',
                                    page_title = "Profile Setup", 
                                    uid = user_id)
        

@app.route('/profile/update/',methods=["GET","POST"])  
def update_profile():
    """
    Handles the update and editing of a user's profile.

    GET: Displays the profile update page with the user's current profile data.

    POST: Updates the user's profile with the new information provided. If the 
    update is successful, redirects to the updated profile page with a success 
    message. If the update fails, displays an error message and re-renders the 
    profile update page with the current data.

    If the user session has expired, redirects to the login page with an 
    appropriate message.
    """
    if not is_logged_in():
        return redirect(url_for('index'))  # Redirect to login page
    user_id = session.get('user_id')
    conn = dbi.connect()

    if request.method == "POST":
        delete_file = request.form.get('delete_file')
        f = request.files['pic']
        if delete_file == 'yes': #if user is deleting a profile pic 
            result = user_db.serve_profile_picture(conn, user_id) #return dict with one key-val pair or None
            if result: #if file exists
                filename = result['filename'] #get filename 
                picture_path = os.path.join(app.config['PROFILE_UPLOADS'],filename) #generate a file path 
                if os.path.exists(picture_path) and os.path.isfile(picture_path):
                    os.remove(picture_path)
                    user_db.delete_profile_pic(conn,user_id) #delete filename from user_file table 
                    flash("Profile picture deleted successfully.")

        elif f.filename != '': #uploading new profile pic 
            user_filename = f.filename
            ext = user_filename.split('.')[-1]
            allowed_extensions = {'png', 'jpg', 'jpeg'}
            if ext not in allowed_extensions: #check if ext of this image is one of the allowed ones 
                flash("Invalid file type. Only image files are allowed.") #if not, flash a message and bring user back to profile update form 
                profile_data = user_db.get_profile(conn,user_id) #get profile data using user_id as key
                if profile_data.get('phone_number') is None: 
                    profile_data['phone_number'] = "" 
                #renders profile update form with current profile data, user_id, and image source (None if profile pic not uploaded)
                return render_template('profile/update.html',
                                        page_title = "Profile Update", 
                                        profile_data=profile_data,
                                        uid = user_id,
                                        src = url_for('profile_pic', user_id = user_id))

            filename = secure_filename('{}.{}'.format(user_id,ext)) #generate new filename using user_id and ext 
            pathname = os.path.join(app.config['PROFILE_UPLOADS'],filename) #generate a file path 
            f.save(pathname)
            user_db.upload_profile_pic(conn,user_id,filename) #update profile pic (filename,uid) to `picfile` db table
        #gets all user data
        user_data = dict(request.form) #convert it to dict(), since request.form is immutable 
        #get career_interests, which might be a list of multiple strings, from the form 
        career_interests = request.form.getlist('career_interests[]')
        career_interests_string = ', '.join(career_interests) #convert to a string of comma-separated career interest(s)
        user_data['career_interests'] = career_interests_string 
        user_data = helper.convert_to_bool(user_data) #convert string bool values to real bool values 
        user_data = helper.convert_to_None(user_data) #convert '' or 'None' values to None 
        try: 
            user_db.update_profile(conn,user_id,user_data) #update this user's profile data 
            flash('Your profile was updated successfully!')
            return redirect(url_for('profile',
                                    user_id = user_id))
        except Exception as err: 
            flash('Failed to update your profile. Please try again')
    #reaches here if request method is GET or if profile update isn't successful 
    profile_data = user_db.get_profile(conn,user_id) #get profile data using user_id as key
    if profile_data.get('phone_number') is None: 
        profile_data['phone_number'] = "" 
    #renders profile update form with current profile data, user_id, and image source (None if profile pic not uploaded)
    return render_template('profile/update.html',
                            page_title = "Profile Update", 
                            profile_data=profile_data,
                            uid = user_id,
                            src = url_for('profile_pic', user_id = user_id))

@app.route('/profile/delete/', methods=["POST"])  
def delete_profile():
    """
    Deletes the user's account by nullifying all profile data except for the name and UID.

    POST: If the user is logged in, their account is deleted, and they are redirected 
    to the welcome page with a success message. If not logged in, they are redirected 
    to the login page. On failure, an error message is shown, and the user is redirected 
    back to their profile page.

    Returns:
        Redirect to the welcome page on success, or back to the profile page on failure.
    """
    user_id = session.get('user_id')
    conn = dbi.connect()
    try:
        # Attempt to delete the user from the database
        user_db.delete_user(conn, user_id) 
        result = user_db.serve_profile_picture(conn,user_id) #return non-empty dict (if profile pic exists) or None 
        if result: #if the user has a profile pic
            filename = result['filename']
            picture_path = os.path.join(app.config['PROFILE_UPLOADS'],filename) #generate a file path 
            if os.path.exists(picture_path) and os.path.isfile(picture_path):
                os.remove(picture_path)
                user_db.delete_profile_pic(conn,user_id) #delete filename from user_file table 
        session.pop('username')
        session.pop('user_id')
        session.pop('logged_in')
        flash('Your account has been successfully deleted. We’re sorry to see you go.')
        return redirect(url_for('index'))  # Redirect to the welcome page (or home page)
    except Exception as err:
        # If there is an error, notify the user
        flash('Something went wrong while deleting your account. Please try again.')
        return redirect(url_for('profile'))  # Redirect back to the profile page
        
@app.route('/search/users/')
def search_users():
    """
    Searches for users based on various filter criteria.

    GET:
    - Retrieves the following query string and search filters from the query parameters:
        - `input`: Partial match on user full name (first name and last name).
        - `class_year`: Filters users by class year (if applicable)
        - `major`: Filters users by major (if applicable)
        - `second_major`: Filters users by second major (if applicable).
        - `minor`: Filters users by minor (if applicable).
        - `job_title`: Filters users by job title (case-insensitive).
        - `current_company`: Filters users by current company (case-insensitive).
        - `career_interests`: Filters users by career interests
    - Searches for users based on the filters provided in the query string.
    - Renders the 'search/users.html,' template with the filtered user list.

    Returns:
        Renders the user search results page with a list of matching users and 
        their profile details. If no matches are found, the page will display 
        relevant message to users. 
    """
    if not is_logged_in():
        return redirect(url_for('index'))  # Redirect to login page
    conn = dbi.connect()
    user_id = session.get('user_id')
    search_dict = request.args
    filtered_users = user_db.search_by_user(conn, search_dict)
    if filtered_users: #if at least one profile matching search is found 
        filtered_users = helper.convert_bool_to_string(filtered_users) #convert boolean values on user profile to descriptive string 
    return render_template('search/users.html', 
                        page_title = "Search Users", 
                        filtered_users = filtered_users,
                        uid = user_id)



#-------------------------#
#  Post & Related Search  #
#-------------------------#
@app.route('/post/<post_id>/', methods=['GET'])
def post(post_id):
    """ 
    Renders the individual post page of the given post id. Displays information
    such as the post header, post author, post id, post type, host name, target
    audience, job role, job level, and post body.
    """
    if not is_logged_in():
        return redirect(url_for('index'))
    
    user_id = session.get('user_id')
    conn = dbi.connect()
    post = post_db.get_post_info(conn, post_id)
    post_info = post_db.format_post_values(post)

    files = post_db.serve_post_file(conn, post_id)  # Fetch files from the database
    file_urls = []

    if files:
        for file in files:
            file['url'] = (url_for('post_file', post_id=post_id, filename=file['filename']))
    
    return render_template('post/view.html', 
                           page_title = post_info['header'],
                           post_id = post_id,
                           post_info = post_info,
                           file_urls = file_urls,
                           files = files,
                           uid = session.get('user_id'))


@app.route('/create_post/', methods=['GET','POST'])
def create_post():
    """ 
    This route allows users to make a post
    Then, redirects to post page after insert. 

    GET:
    Renders a template of a blank form to fill out relevant fields to create a post

    POST:
    After the user fills out the post fields and clicks submit,
    redirects the user to the corresponding individual post page of their new post
    """
    if not is_logged_in():
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    if request.method == 'GET': #no database connection required
        return render_template('post/create.html',
                                page_title = 'Create Post',
                                uid = user_id)
    else:
        conn = dbi.connect()
        new_header = request.form.get('header')
        new_post_type = request.form.get('post_type')
        new_host_name = request.form.get('host_name')
        new_target_audience = request.form.get('target_audience')
        new_job_role = request.form.get('job_role')
        new_job_level = request.form.get('job_level')
        new_post_body = request.form.get('post_body')
        new_files = request.files.getlist('file[]')
        
        #This does the majority of the creation process
        post_id = post_db.create_post(conn, 
                                       new_header, 
                                       new_target_audience, 
                                       new_job_role, 
                                       new_job_level, 
                                       new_host_name, 
                                       new_post_type, 
                                       user_id, 
                                       new_post_body)
                        
        if new_files:
            try:
                for new_file in new_files:
                    if new_file.filename:
                        new_filename = save_post_file(new_file, post_id)
                        post_db.upload_post_file(conn, post_id, new_filename)
                        flash('File successfully uploaded.')
            except Exception as e:
                flash(str(e))
                return redirect(request.url)
        return redirect(url_for('post', post_id = post_id)) 


@app.route('/edit/<post_id>', methods=['GET','POST'])
def edit_post(post_id):
    """ 
    This route allows users to edit an existing post.
    After a user submits update, redirects to the view individual post page of
    that post.
    After a user submits delete, redirects to the home page.
 
    GET:
    Renders an edit form pre-populated with the existing values for post fields.

    POST:
    If update: updates the post with the given input values and redirects to the
        corresponding view post page.
    If delete: deletes the post and redirects to home.

    """
    if not is_logged_in():
        return redirect(url_for('index'))
    
    conn = dbi.connect()
    user_id = session.get('user_id')
    post_info = post_db.get_post_info(conn, post_id)
    
    if user_id != post_info.get('posted_by'):
        flash("Access denied: Only post author is authorized to edit this post.")
        return redirect(url_for('post', post_id = post_id, uid = user_id)) 
        
    elif request.method == 'GET':
        files = post_db.serve_post_file(conn, post_id)  # Fetch files from the database
        if files:
            for file in files:
                file['url'] = url_for('post_file', post_id=post_id, filename=file['filename'])
        return render_template('post/edit.html',
                               page_title = f"Edit Post: {post_info.get('header')}",
                               post_id = post_id,
                               post_info = post_info,
                               files = files,
                               uid = user_id)
    
    elif request.form.get('submit')== 'Delete Entire Post':
        try:
            post_db.delete_post(conn, post_id)
            flash(f"Post({post_info['header']}) was deleted successfully")
        except Exception as e:
            flash("Error deleting post: " + str(e))
        return redirect(url_for('home'))
   
    else: # Update Post
        try:
            input_header = request.form.get('header')
            input_post_type = request.form.get('post_type')
            input_host_name = request.form.get('host_name')
            input_target_audience = request.form.get('target_audience')
            input_job_role = request.form.get('job_role')
            input_job_level = request.form.get('job_level')
            input_post_body = request.form.get('post_body')
            input_file = request.files.get('input_file')

            # Deleting post files
            files_to_delete = request.form.getlist('delete_files[]')
            for file_name in files_to_delete:
                try:
                    post_db.delete_post_file(conn, post_id, file_name)
                    delete_post_file(file_name) # Remove file from directory
                    flash(f"Successfully deleted {file_name}")

                except Exception as err:
                    flash("Error: failed to delete file(s)\n" + str(err))

            updates = post_db.edit_post(conn, 
                                        post_id, 
                                        post_info,
                                        input_header, 
                                        input_post_type, 
                                        input_host_name, 
                                        input_target_audience, 
                                        input_job_role, 
                                        input_job_level, 
                                        input_post_body)
            if updates:
                for field in updates.keys():
                    flash(f"Successfully updated {field}!")
            
            #File upload
            if input_file and input_file.filename:
                try:
                    new_filename = save_post_file(input_file, post_id)
                    post_db.upload_post_file(conn, post_id, new_filename)
                    flash('File successfully uploaded.')
                except Exception as e:
                    flash(str(e))
                    return redirect(request.url)
            # No updates
            elif not (updates or input_file or input_file.filename or files_to_delete):
                flash("No changes were made to the post.")
            #show updated post page
            return redirect(url_for('post', post_id=post_id))
        except Exception as e:
            flash(f"An unexpected error occurred: {str(e)}. Please try again.")
            return redirect(url_for('home'))


@app.route('/search/posts/', methods=['GET'])
def search_posts():
    """
    Initially renders a page with several search filters and the most recent posts.
    Once a user (selects 0 or more filters and) presses the search button,
    it searches for posts that match the input queries and renders a page that
    contains a list of matching posts (as well as the most recent posts below them).
    Can currenly filter by:
        - a general text-based search query that matches header or post body
        - a dropdown for post type
        - a text-based search for host name
        - a text-based search for job role
        - a radio button selection for target audience
    """
    if not is_logged_in():
        return redirect(url_for('index'))
    conn = dbi.connect()
    num_posts = 10
    recent_posts = post_db.get_latest_posts(conn, num_posts)
    user_input = request.args.get('user-input')
    audience_value = request.args.get('target-audience')
    type_value = request.args.get('post-type')
    if type_value == "none":
        type_value = None 
    host_value = request.args.get('host-name')
    role_value = request.args.get('job-role')
    filtered_posts = post_db.search_posts(conn, 
                                        user_input, 
                                        audience_value, 
                                        type_value, 
                                        host_value, 
                                        role_value)
    return render_template('search/posts.html',
                            page_title = "Search Posts",
                            recent_posts = recent_posts, 
                            filtered_posts = filtered_posts, 
                            uid = session.get('user_id'))
 
 
###### POST HELPER FUNCTIONS ######
def save_post_file(file, post_id):
    """Validates and saves an uploaded file."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}
    if file and file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError("Invalid file type. Allowed: png, jpg, jpeg, webp, pdf, doc, docx, xls, xlsx.")
        new_filename = secure_filename(f"{post_id}_{file.filename}")
        save_path = os.path.join(app.config['POST_UPLOADS'], new_filename)
        file.save(save_path)
        return new_filename
    return None


def delete_post_file(filename):
    """Deletes a file from the POST_UPLOADS directory."""
    file_path = os.path.join(app.config['POST_UPLOADS'], filename)
    os.remove(file_path)


#-------------------------#
#       Mentorship        #
#-------------------------#
@app.route('/mentorship/', methods=['GET', 'POST'])  
def mentorship():
    """
    Renders a template with a filler form to get mentorship information
    (Currently does not do anything with this data in the backend)
    """
    if not is_logged_in():
        return redirect(url_for('index'))

    user_id = session.get('user_id')

    if request.method == "GET":
        # Filler form template
        return render_template('mentorship.html',page_title = 'Mentorship Form', uid = user_id)
    else:
        flash("Thank you for filling out the mentorship form!")
        # Redirect user to home page
        return redirect(url_for('home'))


# Entry Point
if __name__ == '__main__':
    import sys, os
    if len(sys.argv) > 1:
        # arg, if any, is the desired port number
        port = int(sys.argv[1])
        assert(port>1024)
    else:
        port = os.getuid()
    db_to_use = 'wwtc_db' # team db
    print(f'will connect to {db_to_use}')
    dbi.conf(db_to_use)
    app.debug = True
    app.run('0.0.0.0',port)