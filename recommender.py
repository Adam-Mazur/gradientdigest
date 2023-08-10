def update_user_profile(user_vector, document_vector, alpha, beta, gamma):
    # P' = alpha * P + beta * D
    for key in user_vector:
        user_vector[key] *= alpha
    for key in document_vector:
        if key not in user_vector:
            user_vector[key] = beta * document_vector[key]
        else:
            user_vector[key] += beta * document_vector[key]

    # Delete very low weights
    for key in user_vector:
        if user_vector[key] < gamma:
            user_vector.pop(key)

    return user_vector

def cosine(vector1, vector2):
    vector1_length = 0
    vector2_length = 0
    dot_product = 0
    for key in vector1:
        vector1_length += vector1[key]**2
        if key in vector2:
            dot_product += vector1[key] * vector2[key]
    for key in vector2:
        vector2_length += vector2[key]**2
    vector1_length = vector1_length**0.5
    vector2_length = vector2_length**0.5
    return dot_product/(vector1_length*vector2_length)
    